"""Database models for CampusConnect."""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


def localnow():
    # Form dates/times are entered in the local campus time zone; keep naive
    # local timestamps consistent throughout this local SQLite application.
    return datetime.now()


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


class Idea(db.Model):
    __tablename__ = "ideas"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="Submitted", index=True)
    admin_notes = db.Column(db.Text, nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=localnow, onupdate=localnow)
    author = db.relationship("User", backref=db.backref("ideas", lazy=True))
    votes = db.relationship("IdeaVote", backref="idea", cascade="all, delete-orphan", lazy=True)

    @property
    def vote_count(self):
        return len(self.votes)


class IdeaVote(db.Model):
    __tablename__ = "idea_votes"
    id = db.Column(db.Integer, primary_key=True)
    idea_id = db.Column(db.Integer, db.ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow)
    __table_args__ = (db.UniqueConstraint("idea_id", "user_id", name="uq_idea_vote_user"),)


class Feedback(db.Model):
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    anonymous_display = db.Column(db.Boolean, nullable=False, default=False)
    admin_response = db.Column(db.Text, nullable=True)
    reviewed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow, index=True)
    author = db.relationship("User", backref=db.backref("feedback_entries", lazy=True))
    __table_args__ = (db.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_rating"),)


class Complaint(db.Model):
    __tablename__ = "complaints"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(140), nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    location = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="Normal")
    status = db.Column(db.String(30), nullable=False, default="Pending", index=True)
    resolution_notes = db.Column(db.Text, nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=localnow, onupdate=localnow)
    author = db.relationship("User", backref=db.backref("complaints", lazy=True))


class Poll(db.Model):
    __tablename__ = "polls"
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(220), nullable=False)
    description = db.Column(db.Text, nullable=True)
    opens_at = db.Column(db.DateTime, nullable=True)
    closes_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Draft", index=True)
    results_public = db.Column(db.Boolean, nullable=False, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow)
    options = db.relationship("PollOption", backref="poll", cascade="all, delete-orphan", lazy=True, order_by="PollOption.id")
    votes = db.relationship("PollVote", backref="poll", cascade="all, delete-orphan", lazy=True)

    @property
    def total_votes(self):
        return len(self.votes)

    def current_state(self, now=None):
        now = now or localnow()
        if self.status == "Draft":
            return "Draft"
        if self.status == "Archived":
            return "Archived"
        if self.status == "Closed" or (self.closes_at and now >= self.closes_at):
            return "Closed"
        if self.opens_at and now < self.opens_at:
            return "Upcoming"
        if self.status == "Published":
            return "Active"
        return self.status


class PollOption(db.Model):
    __tablename__ = "poll_options"
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey("polls.id", ondelete="CASCADE"), nullable=False, index=True)
    text = db.Column(db.String(160), nullable=False)
    votes = db.relationship("PollVote", backref="option", cascade="all, delete-orphan", lazy=True)

    @property
    def vote_count(self):
        return len(self.votes)


class PollVote(db.Model):
    __tablename__ = "poll_votes"
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey("polls.id", ondelete="CASCADE"), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey("poll_options.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow)
    __table_args__ = (
        db.UniqueConstraint("poll_id", "user_id", name="uq_poll_vote_user"),
        db.Index("ix_poll_vote_option", "option_id"),
    )


class Notice(db.Model):
    __tablename__ = "notices"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    published_at = db.Column(db.DateTime, nullable=False, default=localnow)
    event_at = db.Column(db.DateTime, nullable=True)
    registration_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Draft", index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class LostFoundListing(db.Model):
    __tablename__ = "lost_found_listings"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_name = db.Column(db.String(140), nullable=False)
    item_type = db.Column(db.String(10), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(120), nullable=False)
    item_date = db.Column(db.Date, nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Open", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow)
    author = db.relationship("User", backref=db.backref("lost_found_listings", lazy=True))


class ResourceListing(db.Model):
    __tablename__ = "resource_listings"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    listing_type = db.Column(db.String(10), nullable=False, index=True)  # Offer or Request
    subject = db.Column(db.String(100), nullable=True)
    condition = db.Column(db.String(30), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="Available", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow)
    author = db.relationship("User", backref=db.backref("resource_listings", lazy=True))


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action_type = db.Column(db.String(60), nullable=False)
    record_type = db.Column(db.String(60), nullable=False)
    record_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=localnow, index=True)
    actor = db.relationship("User", backref=db.backref("activity_logs", lazy=True))
