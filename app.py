"""CampusConnect: a student-engagement and college-improvement portal.

Run locally with: flask --app app.py run --debug
"""
import os
import re
import uuid
from datetime import datetime, date
from functools import wraps
from urllib.parse import urlparse

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import event, func, or_
from sqlalchemy.engine import Engine
from werkzeug.utils import secure_filename

from config import Config
from extensions import csrf, db
from models import (
    ActivityLog, Complaint, Feedback, Idea, IdeaVote, LostFoundListing, Notice,
    Poll, PollOption, PollVote, ResourceListing, User,
)

IDEA_CATEGORIES = ["Library", "Hostel", "Canteen", "Classrooms", "Laboratories", "Sports", "Internet & Wi-Fi", "Cleanliness", "Clubs & Activities", "Other"]
FEEDBACK_CATEGORIES = ["Classrooms", "Laboratories", "Library", "Hostel", "Canteen", "Transport", "Wi-Fi", "Cleanliness", "Other"]
COMPLAINT_CATEGORIES = ["Electrical", "Furniture", "Laboratory Equipment", "Water Supply", "Wi-Fi", "Cleanliness", "Hostel Maintenance", "Other"]
NOTICE_CATEGORIES = ["College Notice", "Workshop", "Hackathon", "Cultural Event", "Sports", "Examination", "Internship", "Club Activity", "Deadline", "Other"]
LISTING_CATEGORIES = ["Electronics", "ID / Cards", "Books / Notes", "Clothing", "Keys", "Accessories", "Other"]
RESOURCE_CATEGORIES = ["Textbook", "Reference Book", "Study Guide", "Notes", "Lab Manual", "Other"]
IDEA_STATUSES = ["Submitted", "Under Review", "Approved", "In Progress", "Implemented", "Rejected"]
COMPLAINT_STATUSES = ["Pending", "In Progress", "Resolved", "Rejected"]
POLL_STATUSES = ["Draft", "Published", "Closed", "Archived"]

app = Flask(__name__, instance_relative_config=True)
app.config.from_object(Config)
os.makedirs(app.instance_path, exist_ok=True)
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
db.init_app(app)
csrf.init_app(app)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """SQLite leaves FK constraints off by default; enable them per connection."""
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


with app.app_context():
    # create_all creates missing tables without deleting existing user data.
    db.create_all()


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = db.session.get(User, user_id) if user_id else None
    if user_id and g.user is None:
        session.clear()


@app.context_processor
def inject_common_template_values():
    return {"current_user": g.get("user"), "today": date.today()}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        if not g.user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def owner_or_admin(record):
    if not g.user or (not g.user.is_admin and getattr(record, "user_id", None) != g.user.id):
        abort(403)


def log_admin(action_type, record_type, record_id, description):
    """Record important admin actions without saving sensitive contents."""
    entry = ActivityLog(
        actor_id=g.user.id if g.user else None,
        action_type=action_type,
        record_type=record_type,
        record_id=record_id,
        description=description[:300],
    )
    db.session.add(entry)


def clean_text(value, max_length=None):
    value = (value or "").strip()
    if max_length is not None:
        value = value[:max_length]
    return value


def parse_datetime(value):
    value = clean_text(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def parse_date(value):
    value = clean_text(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_valid_http_url(value):
    if not value:
        return True
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def save_image(upload):
    """Save a small, validated image using a randomized filename."""
    if not upload or not upload.filename:
        return None, None
    original = secure_filename(upload.filename)
    if not original or "." not in original:
        return None, "Choose a valid image file."
    extension = original.rsplit(".", 1)[1].lower()
    allowed = {"png", "jpg", "jpeg", "gif", "webp"}
    if extension not in allowed:
        return None, "Allowed image types are PNG, JPG, JPEG, GIF, and WEBP."
    filename = f"{uuid.uuid4().hex}.{extension}"
    upload.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename, None


def image_url(filename):
    return url_for("static", filename=f"uploads/{filename}") if filename else None


def form_field(name, label, kind="text", value="", required=False, options=None, help_text=None, accept=None):
    return {"name": name, "label": label, "type": kind, "value": value or "", "required": required,
            "options": options or [], "help": help_text, "accept": accept}


def show_form(title, subtitle, fields, action_url, submit_label="Save", multipart=False):
    return render_template("form.html", title=title, subtitle=subtitle, fields=fields,
                           action_url=action_url, submit_label=submit_label, multipart=multipart)


def list_item(title, text, badge="", meta="", url="#", extra=None):
    result = {"title": title, "text": text or "", "badge": badge or "", "meta": meta or "", "url": url}
    if extra:
        result.update(extra)
    return result


def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    stats = {
        "ideas": Idea.query.count(),
        "notices": Notice.query.filter_by(status="Published").count(),
        "students": User.query.filter_by(role="student").count(),
    }
    latest_notices = Notice.query.filter_by(status="Published").order_by(Notice.published_at.desc()).limit(3).all()
    return render_template("index.html", stats=stats, latest_notices=latest_notices)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = clean_text(request.form.get("name"), 80)
        email = clean_text(request.form.get("email"), 160).lower()
        password = request.form.get("password", "")
        errors = []
        if len(name) < 2:
            errors.append("Enter your full name (at least 2 characters).")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must contain at least 8 characters.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            user = User(name=name, email=email, role="student")  # Public registration is always student.
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Account created. You can now log in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = clean_text(request.form.get("email"), 160).lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash("Email or password is incorrect.", "danger")
        else:
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            flash(f"Welcome back, {user.name.split()[0]}!", "success")
            next_url = request.args.get("next", "")
            # Do not redirect to an external URL.
            if next_url.startswith("/") and not next_url.startswith(("//", "/\\")) and not urlparse(next_url).netloc:
                return redirect(next_url)
            return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    if g.user.is_admin:
        return redirect(url_for("admin_dashboard"))
    my_ideas = Idea.query.filter_by(user_id=g.user.id).order_by(Idea.created_at.desc()).limit(4).all()
    my_complaints = Complaint.query.filter_by(user_id=g.user.id).order_by(Complaint.created_at.desc()).limit(4).all()
    latest_notices = Notice.query.filter_by(status="Published").order_by(Notice.published_at.desc()).limit(4).all()
    active_polls = [p for p in Poll.query.filter_by(status="Published").order_by(Poll.created_at.desc()).all() if p.current_state() in {"Active", "Upcoming"}][:3]
    metrics = {
        "ideas": Idea.query.count(),
        "open_complaints": Complaint.query.filter(Complaint.status.in_(["Pending", "In Progress"])).count(),
        "published_notices": Notice.query.filter_by(status="Published").count(),
        "active_polls": len([p for p in Poll.query.filter_by(status="Published").all() if p.current_state() == "Active"]),
    }
    return render_template("dashboard.html", my_ideas=my_ideas, my_complaints=my_complaints,
                           latest_notices=latest_notices, active_polls=active_polls, metrics=metrics)


# ------------------------------ A. IDEA HUB ------------------------------
@app.route("/ideas")
@login_required
def idea_list():
    query = Idea.query
    q = clean_text(request.args.get("q"), 100)
    category = request.args.get("category", "")
    status = request.args.get("status", "")
    if q:
        query = query.filter(or_(Idea.title.ilike(f"%{q}%"), Idea.description.ilike(f"%{q}%")))
    if category in IDEA_CATEGORIES:
        query = query.filter_by(category=category)
    if status in IDEA_STATUSES:
        query = query.filter_by(status=status)
    sort = request.args.get("sort", "newest")
    if sort == "votes":
        query = query.outerjoin(IdeaVote).group_by(Idea.id).order_by(func.count(IdeaVote.id).desc(), Idea.created_at.desc())
    else:
        query = query.order_by(Idea.created_at.desc())
    ideas = query.limit(100).all()
    items = [list_item(i.title, i.description[:185] + ("…" if len(i.description) > 185 else ""), i.status,
                       f"{i.category} · {i.vote_count} votes · {i.created_at:%d %b %Y}", url_for("idea_detail", idea_id=i.id)) for i in ideas]
    return render_template("list.html", title="Student Idea Hub", subtitle="Turn practical campus suggestions into trackable action.",
                           items=items, create_url=url_for("idea_create"), create_label="Submit an idea", empty_message="No ideas match these filters.",
                           filters={"q": q, "category": category, "status": status, "sort": sort}, categories=IDEA_CATEGORIES,
                           statuses=IDEA_STATUSES, filter_kind="ideas")


@app.route("/ideas/new", methods=["GET", "POST"])
@login_required
def idea_create():
    if request.method == "POST":
        title = clean_text(request.form.get("title"), 140)
        description = clean_text(request.form.get("description"))
        category = request.form.get("category", "")
        filename, upload_error = save_image(request.files.get("image"))
        errors = []
        if not title: errors.append("Title is required.")
        if len(description) < 10: errors.append("Please provide a description of at least 10 characters.")
        if category not in IDEA_CATEGORIES: errors.append("Choose a valid category.")
        if upload_error: errors.append(upload_error)
        if errors:
            for error in errors: flash(error, "danger")
        else:
            idea = Idea(user_id=g.user.id, title=title, description=description, category=category, image_filename=filename)
            db.session.add(idea)
            db.session.commit()
            flash("Your idea was submitted and is now trackable in My Activity.", "success")
            return redirect(url_for("idea_detail", idea_id=idea.id))
    fields = [form_field("title", "Idea title", required=True), form_field("category", "Category", "select", required=True, options=[(x, x) for x in IDEA_CATEGORIES]),
              form_field("description", "Describe the problem and your proposed improvement", "textarea", required=True),
              form_field("image", "Optional image", "file", accept="image/png,image/jpeg,image/gif,image/webp", help_text="PNG, JPG, GIF or WEBP; up to 2 MB.")]
    return show_form("Submit an idea", "Be specific about the campus issue and the improvement you propose.", fields, url_for("idea_create"), "Submit idea", True)


@app.route("/ideas/<int:idea_id>")
@login_required
def idea_detail(idea_id):
    idea = db.get_or_404(Idea, idea_id)
    own_vote = IdeaVote.query.filter_by(idea_id=idea.id, user_id=g.user.id).first() is not None
    return render_template("detail.html", kind="idea", title=idea.title, subtitle=f"Idea #{idea.id} · {idea.category}",
                           record=idea, own_vote=own_vote, image=image_url(idea.image_filename))


@app.post("/ideas/<int:idea_id>/vote")
@login_required
def idea_vote(idea_id):
    idea = db.get_or_404(Idea, idea_id)
    existing = IdeaVote.query.filter_by(idea_id=idea.id, user_id=g.user.id).first()
    if existing:
        db.session.delete(existing)
        flash("Your vote was removed.", "info")
    else:
        db.session.add(IdeaVote(idea_id=idea.id, user_id=g.user.id))
        flash("Your vote was recorded.", "success")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Your vote could not be saved. Please try again.", "danger")
    return redirect(url_for("idea_detail", idea_id=idea.id))


@app.route("/ideas/<int:idea_id>/edit", methods=["GET", "POST"])
@login_required
def idea_edit(idea_id):
    idea = db.get_or_404(Idea, idea_id)
    owner_or_admin(idea)
    if not g.user.is_admin and idea.status != "Submitted":
        abort(403)
    if request.method == "POST":
        title = clean_text(request.form.get("title"), 140)
        description = clean_text(request.form.get("description"))
        category = request.form.get("category", "")
        filename, upload_error = save_image(request.files.get("image"))
        errors = []
        if not title: errors.append("Title is required.")
        if len(description) < 10: errors.append("Description must be at least 10 characters.")
        if category not in IDEA_CATEGORIES: errors.append("Choose a valid category.")
        if upload_error: errors.append(upload_error)
        if errors:
            for error in errors: flash(error, "danger")
        else:
            idea.title, idea.description, idea.category = title, description, category
            if filename: idea.image_filename = filename
            if g.user.is_admin:
                log_admin("idea_edit", "Idea", idea.id, f"Idea #{idea.id} was edited by an administrator.")
            db.session.commit()
            flash("Idea updated.", "success")
            return redirect(url_for("idea_detail", idea_id=idea.id))
    fields = [form_field("title", "Idea title", value=idea.title, required=True),
              form_field("category", "Category", "select", value=idea.category, required=True, options=[(x, x) for x in IDEA_CATEGORIES]),
              form_field("description", "Description", "textarea", value=idea.description, required=True),
              form_field("image", "Replace image (optional)", "file", accept="image/png,image/jpeg,image/gif,image/webp")]
    return show_form("Edit idea", "Only submitted ideas can be edited by students.", fields, url_for("idea_edit", idea_id=idea.id), "Save changes", True)


@app.post("/ideas/<int:idea_id>/delete")
@login_required
def idea_delete(idea_id):
    idea = db.get_or_404(Idea, idea_id)
    owner_or_admin(idea)
    if not g.user.is_admin and idea.status != "Submitted": abort(403)
    if g.user.is_admin:
        log_admin("idea_delete", "Idea", idea.id, f"Idea #{idea.id} was removed by an administrator.")
    db.session.delete(idea)
    db.session.commit()
    flash("Idea deleted.", "success")
    return redirect(url_for("idea_list"))


@app.post("/admin/ideas/<int:idea_id>/status")
@admin_required
def idea_update_status(idea_id):
    idea = db.get_or_404(Idea, idea_id)
    status = request.form.get("status", "")
    notes = clean_text(request.form.get("admin_notes"), 3000)
    if status not in IDEA_STATUSES:
        flash("Choose a valid idea status.", "danger")
    elif status == "Rejected" and len(notes) < 5:
        flash("Add a short reason when rejecting an idea.", "danger")
    else:
        idea.status, idea.admin_notes = status, notes
        log_admin("idea_status", "Idea", idea.id, f"Idea #{idea.id} marked {status}.")
        db.session.commit()
        flash("Idea status updated.", "success")
    return redirect(url_for("idea_detail", idea_id=idea.id))


# ---------------------------- B. FEEDBACK -------------------------------
@app.route("/feedback")
@login_required
def feedback_list():
    is_admin = g.user.is_admin
    category = request.args.get("category", "")
    query = Feedback.query if is_admin else Feedback.query.filter_by(user_id=g.user.id)
    if category in FEEDBACK_CATEGORIES:
        query = query.filter_by(category=category)
    entries = query.order_by(Feedback.created_at.desc()).limit(150).all()
    items = [list_item(f"{f.category} · {f.rating}/5", f.comment[:200], "Reviewed" if f.reviewed else "Awaiting review",
                       f"{f.created_at:%d %b %Y}" + (" · Anonymous display" if f.anonymous_display else ""), url_for("feedback_detail", feedback_id=f.id)) for f in entries]
    averages = db.session.query(Feedback.category, func.avg(Feedback.rating), func.count(Feedback.id)).group_by(Feedback.category).all()
    return render_template("list.html", title="Feedback & Ratings", subtitle="Share constructive feedback about college facilities.",
                           items=items, create_url=url_for("feedback_create"), create_label="Give feedback", empty_message="No feedback entries found.",
                           filters={"category": category}, categories=FEEDBACK_CATEGORIES, filter_kind="feedback",
                           extra_stats=[{"label": cat, "value": f"{avg:.1f}/5", "detail": f"{count} rating(s)"} for cat, avg, count in averages])


@app.route("/feedback/new", methods=["GET", "POST"])
@login_required
def feedback_create():
    if request.method == "POST":
        category = request.form.get("category", "")
        rating = parse_int(request.form.get("rating"))
        comment = clean_text(request.form.get("comment"), 2000)
        anonymous = request.form.get("anonymous_display") == "on"
        errors = []
        if category not in FEEDBACK_CATEGORIES: errors.append("Choose a valid facility category.")
        if rating not in [1, 2, 3, 4, 5]: errors.append("Rating must be between 1 and 5.")
        if len(comment) < 5: errors.append("Comment must contain at least 5 characters.")
        if errors:
            for error in errors: flash(error, "danger")
        else:
            entry = Feedback(user_id=g.user.id, category=category, rating=rating, comment=comment, anonymous_display=anonymous)
            db.session.add(entry)
            db.session.commit()
            flash("Feedback submitted. Your personal history remains private to you and administrators.", "success")
            return redirect(url_for("feedback_detail", feedback_id=entry.id))
    fields = [form_field("category", "Facility", "select", required=True, options=[(x, x) for x in FEEDBACK_CATEGORIES]),
              form_field("rating", "Rating (1–5)", "select", required=True, options=[(str(x), f"{x} / 5") for x in range(5, 0, -1)]),
              form_field("comment", "Your feedback", "textarea", required=True, help_text="Be respectful and specific. Maximum 2,000 characters."),
              form_field("anonymous_display", "Do not show my name in feedback displays", "checkbox", value=False,
                         help_text="Administrators can still see the account connected to the submission.")]
    return show_form("Give feedback", "Help the college identify strengths and areas for improvement.", fields, url_for("feedback_create"), "Submit feedback")


@app.route("/feedback/<int:feedback_id>")
@login_required
def feedback_detail(feedback_id):
    entry = db.get_or_404(Feedback, feedback_id)
    if not g.user.is_admin and entry.user_id != g.user.id:
        abort(403)
    return render_template("detail.html", kind="feedback", title=f"{entry.category} feedback", subtitle=f"Feedback #{entry.id} · {entry.rating}/5",
                           record=entry, image=None)


@app.post("/admin/feedback/<int:feedback_id>/respond")
@admin_required
def feedback_respond(feedback_id):
    entry = db.get_or_404(Feedback, feedback_id)
    response = clean_text(request.form.get("admin_response"), 2000)
    if len(response) < 2:
        flash("Enter a response before saving.", "danger")
    else:
        entry.admin_response = response
        entry.reviewed = True
        log_admin("feedback_response", "Feedback", entry.id, f"Responded to feedback #{entry.id}.")
        db.session.commit()
        flash("Feedback response saved.", "success")
    return redirect(url_for("feedback_detail", feedback_id=entry.id))


@app.post("/admin/feedback/<int:feedback_id>/moderate")
@admin_required
def feedback_moderate(feedback_id):
    entry = db.get_or_404(Feedback, feedback_id)
    action = request.form.get("action")
    if action == "review":
        entry.reviewed = True
        log_admin("feedback_review", "Feedback", entry.id, f"Marked feedback #{entry.id} reviewed.")
        db.session.commit()
        flash("Feedback marked as reviewed.", "success")
    elif action == "delete":
        log_admin("feedback_moderate_delete", "Feedback", entry.id, f"Moderated feedback #{entry.id}.")
        db.session.delete(entry)
        db.session.commit()
        flash("Feedback removed.", "success")
    else:
        flash("Invalid moderation action.", "danger")
    return redirect(url_for("feedback_list"))


# --------------------------- C. COMPLAINTS ------------------------------
@app.route("/complaints")
@login_required
def complaint_list():
    query = Complaint.query if g.user.is_admin else Complaint.query.filter_by(user_id=g.user.id)
    q = clean_text(request.args.get("q"), 100)
    status = request.args.get("status", "")
    category = request.args.get("category", "")
    if q:
        query = query.filter(or_(Complaint.title.ilike(f"%{q}%"), Complaint.description.ilike(f"%{q}%"), Complaint.location.ilike(f"%{q}%")))
    if status in COMPLAINT_STATUSES: query = query.filter_by(status=status)
    if category in COMPLAINT_CATEGORIES: query = query.filter_by(category=category)
    complaints = query.order_by(Complaint.created_at.desc()).limit(150).all()
    items = [list_item(c.title, c.description[:160], c.status, f"{c.category} · {c.location} · {c.priority} priority · {c.created_at:%d %b %Y}", url_for("complaint_detail", complaint_id=c.id)) for c in complaints]
    return render_template("list.html", title="Campus Complaints", subtitle="Report a maintenance issue and track its resolution.", items=items,
                           create_url=url_for("complaint_create"), create_label="Report a problem", empty_message="No complaints found.",
                           filters={"q": q, "status": status, "category": category}, categories=COMPLAINT_CATEGORIES,
                           statuses=COMPLAINT_STATUSES, filter_kind="complaints")


@app.route("/complaints/new", methods=["GET", "POST"])
@login_required
def complaint_create():
    if request.method == "POST":
        title = clean_text(request.form.get("title"), 140)
        category = request.form.get("category", "")
        location = clean_text(request.form.get("location"), 120)
        description = clean_text(request.form.get("description"))
        filename, upload_error = save_image(request.files.get("image"))
        errors = []
        if not title: errors.append("Title is required.")
        if category not in COMPLAINT_CATEGORIES: errors.append("Choose a valid category.")
        if len(location) < 2: errors.append("Enter the campus location.")
        if len(description) < 10: errors.append("Description must contain at least 10 characters.")
        if upload_error: errors.append(upload_error)
        if errors:
            for error in errors: flash(error, "danger")
        else:
            complaint = Complaint(user_id=g.user.id, title=title, category=category, location=location, description=description, image_filename=filename)
            db.session.add(complaint)
            db.session.commit()
            flash("Complaint submitted. You can track its status here.", "success")
            return redirect(url_for("complaint_detail", complaint_id=complaint.id))
    fields = [form_field("title", "Problem title", required=True), form_field("category", "Category", "select", required=True, options=[(x, x) for x in COMPLAINT_CATEGORIES]),
              form_field("location", "Campus location", required=True), form_field("description", "Describe the problem", "textarea", required=True),
              form_field("image", "Optional image", "file", accept="image/png,image/jpeg,image/gif,image/webp", help_text="PNG, JPG, GIF or WEBP; up to 2 MB.")]
    return show_form("Report a campus problem", "Do not include personal or sensitive information in the description.", fields, url_for("complaint_create"), "Submit complaint", True)


@app.route("/complaints/<int:complaint_id>")
@login_required
def complaint_detail(complaint_id):
    complaint = db.get_or_404(Complaint, complaint_id)
    if not g.user.is_admin and complaint.user_id != g.user.id: abort(403)
    return render_template("detail.html", kind="complaint", title=complaint.title, subtitle=f"Complaint #{complaint.id} · {complaint.category}",
                           record=complaint, image=image_url(complaint.image_filename))


@app.post("/admin/complaints/<int:complaint_id>/update")
@admin_required
def complaint_update(complaint_id):
    complaint = db.get_or_404(Complaint, complaint_id)
    status = request.form.get("status", "")
    priority = request.form.get("priority", "")
    notes = clean_text(request.form.get("resolution_notes"), 3000)
    if status not in COMPLAINT_STATUSES or priority not in ["Low", "Normal", "High", "Urgent"]:
        flash("Choose a valid status and priority.", "danger")
    elif status == "Resolved" and len(notes) < 3:
        flash("Add resolution notes before marking a complaint resolved.", "danger")
    else:
        old_status = complaint.status
        complaint.status, complaint.priority, complaint.resolution_notes = status, priority, notes
        log_admin("complaint_update", "Complaint", complaint.id, f"Complaint #{complaint.id}: {old_status} → {status}; priority {priority}.")
        db.session.commit()
        flash("Complaint updated.", "success")
    return redirect(url_for("complaint_detail", complaint_id=complaint.id))


# ------------------------------ D. POLLS --------------------------------
def poll_fields(poll=None):
    options_text = "\n".join(option.text for option in poll.options) if poll else ""
    return [form_field("question", "Poll question", value=poll.question if poll else "", required=True),
            form_field("description", "Description (optional)", "textarea", value=poll.description if poll else ""),
            form_field("options", "Options (one per line; at least two)", "textarea", value=options_text, required=True),
            form_field("opens_at", "Opens at (optional)", "datetime-local", value=poll.opens_at.strftime("%Y-%m-%dT%H:%M") if poll and poll.opens_at else ""),
            form_field("closes_at", "Closes at (optional)", "datetime-local", value=poll.closes_at.strftime("%Y-%m-%dT%H:%M") if poll and poll.closes_at else ""),
            form_field("status", "Publication status", "select", value=poll.status if poll else "Draft", required=True, options=[(x, x) for x in POLL_STATUSES]),
            form_field("results_public", "Show results to students before the poll closes", "checkbox", value=poll.results_public if poll else False)]


def save_poll_from_form(poll, is_new=False):
    question = clean_text(request.form.get("question"), 220)
    description = clean_text(request.form.get("description"), 3000)
    options = [clean_text(line, 160) for line in request.form.get("options", "").splitlines()]
    options = list(dict.fromkeys([o for o in options if o]))
    status = request.form.get("status", "Draft")
    opens_at = parse_datetime(request.form.get("opens_at"))
    closes_at = parse_datetime(request.form.get("closes_at"))
    errors = []
    if not question: errors.append("Poll question is required.")
    if len(options) < 2: errors.append("Add at least two distinct options, one per line.")
    if status not in POLL_STATUSES: errors.append("Choose a valid poll status.")
    if request.form.get("opens_at") and opens_at is None: errors.append("Opening time is invalid.")
    if request.form.get("closes_at") and closes_at is None: errors.append("Closing time is invalid.")
    if opens_at and closes_at and closes_at <= opens_at: errors.append("Closing time must be after opening time.")
    if poll and PollVote.query.filter_by(poll_id=poll.id).count() and options != [o.text for o in poll.options]:
        errors.append("Options cannot be changed after the first vote has been recorded.")
    if errors:
        for error in errors: flash(error, "danger")
        return False
    poll.question, poll.description, poll.opens_at, poll.closes_at = question, description, opens_at, closes_at
    poll.status = status
    poll.results_public = request.form.get("results_public") == "on"
    if is_new:
        poll.created_by = g.user.id
        db.session.add(poll)
        db.session.flush()
    if not PollVote.query.filter_by(poll_id=poll.id).count():
        PollOption.query.filter_by(poll_id=poll.id).delete(synchronize_session=False)
        for option in options:
            db.session.add(PollOption(poll_id=poll.id, text=option))
    action = "poll_create" if is_new else "poll_update"
    log_admin(action, "Poll", poll.id, f"Poll #{poll.id} saved with status {poll.status}.")
    db.session.commit()
    return True


@app.route("/polls")
@login_required
def poll_list():
    polls = Poll.query.order_by(Poll.created_at.desc()).limit(150).all()
    items = []
    for poll in polls:
        if not g.user.is_admin and poll.status in {"Draft", "Archived"}:
            continue
        state = poll.current_state()
        items.append(list_item(poll.question, poll.description[:160] if poll.description else "Share your view on this campus question.",
                               state, f"{poll.total_votes} vote(s) · {len(poll.options)} options", url_for("poll_detail", poll_id=poll.id)))
    return render_template("list.html", title="Campus Polls", subtitle="Help shape campus decisions by participating in quick polls.",
                           items=items, create_url=url_for("poll_create") if g.user.is_admin else None,
                           create_label="Create poll", empty_message="There are no polls to display.", filter_kind="none")


@app.route("/polls/new", methods=["GET", "POST"])
@admin_required
def poll_create():
    poll = Poll()
    if request.method == "POST" and save_poll_from_form(poll, is_new=True):
        flash("Poll created.", "success")
        return redirect(url_for("poll_detail", poll_id=poll.id))
    return show_form("Create a campus poll", "Use one option per line. At least two distinct options are required.", poll_fields(), url_for("poll_create"), "Create poll")


@app.route("/polls/<int:poll_id>")
@login_required
def poll_detail(poll_id):
    poll = db.get_or_404(Poll, poll_id)
    if not g.user.is_admin and poll.status in {"Draft", "Archived"}: abort(404)
    existing_vote = PollVote.query.filter_by(poll_id=poll.id, user_id=g.user.id).first()
    state = poll.current_state()
    can_vote = (not g.user.is_admin and poll.status == "Published" and state == "Active" and existing_vote is None and len(poll.options) >= 2)
    show_results = g.user.is_admin or poll.results_public or state == "Closed"
    return render_template("detail.html", kind="poll", title=poll.question, subtitle=f"Poll #{poll.id} · {state}",
                           record=poll, existing_vote=existing_vote, can_vote=can_vote, show_results=show_results, image=None)


@app.post("/polls/<int:poll_id>/vote")
@login_required
def poll_vote(poll_id):
    if g.user.is_admin:
        abort(403)
    poll = db.get_or_404(Poll, poll_id)
    if poll.status != "Published" or poll.current_state() != "Active":
        flash("This poll is not currently open for voting.", "warning")
        return redirect(url_for("poll_detail", poll_id=poll.id))
    option_id = parse_int(request.form.get("option_id"))
    option = db.session.get(PollOption, option_id) if option_id else None
    if option is None or option.poll_id != poll.id:
        flash("Choose one of the listed options.", "danger")
    elif PollVote.query.filter_by(poll_id=poll.id, user_id=g.user.id).first():
        flash("You have already voted in this poll.", "warning")
    else:
        db.session.add(PollVote(poll_id=poll.id, option_id=option.id, user_id=g.user.id))
        try:
            db.session.commit()
            flash("Your vote was recorded.", "success")
        except Exception:
            db.session.rollback()
            flash("A vote could not be saved. You may already have voted.", "warning")
    return redirect(url_for("poll_detail", poll_id=poll.id))


@app.route("/polls/<int:poll_id>/edit", methods=["GET", "POST"])
@admin_required
def poll_edit(poll_id):
    poll = db.get_or_404(Poll, poll_id)
    if request.method == "POST" and save_poll_from_form(poll):
        flash("Poll updated.", "success")
        return redirect(url_for("poll_detail", poll_id=poll.id))
    return show_form("Edit poll", "Existing votes are preserved; options lock after the first vote.", poll_fields(poll), url_for("poll_edit", poll_id=poll.id), "Save changes")


@app.post("/admin/polls/<int:poll_id>/status")
@admin_required
def poll_update_status(poll_id):
    poll = db.get_or_404(Poll, poll_id)
    status = request.form.get("status", "")
    if status not in POLL_STATUSES:
        flash("Choose a valid poll status.", "danger")
    elif status == "Published" and len(poll.options) < 2:
        flash("Add at least two options before publishing.", "danger")
    else:
        poll.status = status
        log_admin("poll_status", "Poll", poll.id, f"Poll #{poll.id} status changed to {status}.")
        db.session.commit()
        flash("Poll status updated.", "success")
    return redirect(url_for("poll_detail", poll_id=poll.id))


# ------------------------------- E. NOTICES -----------------------------
@app.route("/notices")
@login_required
def notice_list():
    q = clean_text(request.args.get("q"), 100)
    category = request.args.get("category", "")
    query = Notice.query if g.user.is_admin else Notice.query.filter_by(status="Published")
    if q: query = query.filter(Notice.title.ilike(f"%{q}%"))
    if category in NOTICE_CATEGORIES: query = query.filter_by(category=category)
    notices = query.order_by(Notice.published_at.desc()).limit(150).all()
    items = [list_item(n.title, n.description[:180], n.status, f"{n.category} · {n.published_at:%d %b %Y}" + (f" · Event {n.event_at:%d %b %Y}" if n.event_at else ""), url_for("notice_detail", notice_id=n.id)) for n in notices]
    return render_template("list.html", title="Notices & Events", subtitle="One place for college announcements, events, and important dates.", items=items,
                           create_url=url_for("notice_create") if g.user.is_admin else None, create_label="Publish a notice",
                           empty_message="No notices match your search.", filters={"q": q, "category": category}, categories=NOTICE_CATEGORIES, filter_kind="notices")


def notice_fields(notice=None):
    return [form_field("title", "Notice title", value=notice.title if notice else "", required=True),
            form_field("category", "Category", "select", value=notice.category if notice else "College Notice", required=True, options=[(x, x) for x in NOTICE_CATEGORIES]),
            form_field("description", "Details", "textarea", value=notice.description if notice else "", required=True),
            form_field("published_at", "Publication date/time", "datetime-local", value=notice.published_at.strftime("%Y-%m-%dT%H:%M") if notice else datetime.now().strftime("%Y-%m-%dT%H:%M")),
            form_field("event_at", "Event date/time (optional)", "datetime-local", value=notice.event_at.strftime("%Y-%m-%dT%H:%M") if notice and notice.event_at else ""),
            form_field("registration_url", "Registration URL (optional)", value=notice.registration_url if notice else "", help_text="Must begin with https:// or http://."),
            form_field("status", "Publication status", "select", value=notice.status if notice else "Draft", required=True, options=[(x, x) for x in ["Draft", "Published", "Archived"]])]


def save_notice(notice, is_new=False):
    title = clean_text(request.form.get("title"), 180)
    category = request.form.get("category", "")
    description = clean_text(request.form.get("description"), 8000)
    published_at = parse_datetime(request.form.get("published_at"))
    event_at = parse_datetime(request.form.get("event_at"))
    url = clean_text(request.form.get("registration_url"), 500)
    status = request.form.get("status", "Draft")
    errors = []
    if not title: errors.append("Title is required.")
    if category not in NOTICE_CATEGORIES: errors.append("Choose a valid category.")
    if len(description) < 5: errors.append("Description must contain at least 5 characters.")
    if not published_at: errors.append("Enter a valid publication date and time.")
    if request.form.get("event_at") and not event_at: errors.append("Event date and time are invalid.")
    if not is_valid_http_url(url): errors.append("Registration URL must be a valid HTTP or HTTPS link.")
    if status not in ["Draft", "Published", "Archived"]: errors.append("Choose a valid publication status.")
    if errors:
        for error in errors: flash(error, "danger")
        return False
    notice.title, notice.category, notice.description = title, category, description
    notice.published_at, notice.event_at, notice.registration_url, notice.status = published_at, event_at, url or None, status
    if is_new:
        notice.created_by = g.user.id
        db.session.add(notice)
    db.session.flush()
    log_admin("notice_create" if is_new else "notice_update", "Notice", notice.id, f"Notice #{notice.id} saved with status {status}.")
    db.session.commit()
    return True


@app.route("/notices/new", methods=["GET", "POST"])
@admin_required
def notice_create():
    notice = Notice()
    if request.method == "POST" and save_notice(notice, True):
        flash("Notice saved.", "success")
        return redirect(url_for("notice_detail", notice_id=notice.id))
    return show_form("Create a notice", "Draft notices remain visible only to administrators.", notice_fields(), url_for("notice_create"), "Save notice")


@app.route("/notices/<int:notice_id>")
@login_required
def notice_detail(notice_id):
    notice = db.get_or_404(Notice, notice_id)
    if not g.user.is_admin and notice.status != "Published": abort(404)
    return render_template("detail.html", kind="notice", title=notice.title, subtitle=f"{notice.category} · Notice #{notice.id}", record=notice, image=None)


@app.route("/notices/<int:notice_id>/edit", methods=["GET", "POST"])
@admin_required
def notice_edit(notice_id):
    notice = db.get_or_404(Notice, notice_id)
    if request.method == "POST" and save_notice(notice):
        flash("Notice updated.", "success")
        return redirect(url_for("notice_detail", notice_id=notice.id))
    return show_form("Edit notice", "Check dates and links before publishing.", notice_fields(notice), url_for("notice_edit", notice_id=notice.id), "Save changes")


# ------------------------------ F. LOST & FOUND -------------------------
@app.route("/lost-found")
@login_required
def lost_found_list():
    query = LostFoundListing.query if g.user.is_admin else LostFoundListing.query.filter(LostFoundListing.status == "Open")
    q = clean_text(request.args.get("q"), 100)
    item_type = request.args.get("item_type", "")
    category = request.args.get("category", "")
    if q: query = query.filter(or_(LostFoundListing.item_name.ilike(f"%{q}%"), LostFoundListing.description.ilike(f"%{q}%")))
    if item_type in ["Lost", "Found"]: query = query.filter_by(item_type=item_type)
    if category in LISTING_CATEGORIES: query = query.filter_by(category=category)
    listings = query.order_by(LostFoundListing.created_at.desc()).limit(150).all()
    items = [list_item(f"{l.item_type}: {l.item_name}", l.description[:160], l.status, f"{l.category} · {l.location} · {l.created_at:%d %b %Y}", url_for("lost_found_detail", listing_id=l.id)) for l in listings]
    return render_template("list.html", title="Lost & Found", subtitle="Help return items to their owners without exposing private contact details.", items=items,
                           create_url=url_for("lost_found_create"), create_label="Post an item", empty_message="No matching open listings.",
                           filters={"q": q, "item_type": item_type, "category": category}, categories=LISTING_CATEGORIES,
                           filter_kind="lost_found", type_options=["Lost", "Found"])


def lost_found_fields(listing=None):
    return [form_field("item_name", "Item name", value=listing.item_name if listing else "", required=True),
            form_field("item_type", "Listing type", "select", value=listing.item_type if listing else "Lost", required=True, options=[("Lost", "Lost"), ("Found", "Found")]),
            form_field("category", "Category", "select", value=listing.category if listing else "Other", required=True, options=[(x, x) for x in LISTING_CATEGORIES]),
            form_field("description", "Description", "textarea", value=listing.description if listing else "", required=True),
            form_field("location", "Approximate campus location", value=listing.location if listing else "", required=True),
            form_field("item_date", "Date item was lost/found", "date", value=listing.item_date.isoformat() if listing and listing.item_date else ""),
            form_field("image", "Optional image", "file", accept="image/png,image/jpeg,image/gif,image/webp", help_text="Do not include identity cards or sensitive documents in a photo.")]


def save_lost_found(listing, is_new=False):
    name = clean_text(request.form.get("item_name"), 140)
    item_type = request.form.get("item_type", "")
    category = request.form.get("category", "")
    description = clean_text(request.form.get("description"), 3000)
    location = clean_text(request.form.get("location"), 120)
    item_date = parse_date(request.form.get("item_date"))
    filename, upload_error = save_image(request.files.get("image"))
    errors = []
    if not name: errors.append("Item name is required.")
    if item_type not in ["Lost", "Found"]: errors.append("Choose Lost or Found.")
    if category not in LISTING_CATEGORIES: errors.append("Choose a valid category.")
    if len(description) < 5: errors.append("Description must contain at least 5 characters.")
    if not location: errors.append("Approximate location is required.")
    if request.form.get("item_date") and not item_date: errors.append("Item date is invalid.")
    if upload_error: errors.append(upload_error)
    if errors:
        for error in errors: flash(error, "danger")
        return False
    listing.item_name, listing.item_type, listing.category = name, item_type, category
    listing.description, listing.location, listing.item_date = description, location, item_date
    if filename: listing.image_filename = filename
    if is_new:
        listing.user_id = g.user.id
        db.session.add(listing)
        db.session.flush()
    if g.user.is_admin:
        log_admin("listing_moderation", "LostFoundListing", listing.id, f"Lost/found listing #{listing.id} was saved by an administrator.")
    db.session.commit()
    return True


@app.route("/lost-found/new", methods=["GET", "POST"])
@login_required
def lost_found_create():
    listing = LostFoundListing()
    if request.method == "POST" and save_lost_found(listing, True):
        flash("Listing published. Contact information is not shown publicly.", "success")
        return redirect(url_for("lost_found_detail", listing_id=listing.id))
    return show_form("Post a lost or found item", "Use approximate locations only; do not post phone numbers or personal addresses.", lost_found_fields(), url_for("lost_found_create"), "Publish listing", True)


@app.route("/lost-found/<int:listing_id>")
@login_required
def lost_found_detail(listing_id):
    listing = db.get_or_404(LostFoundListing, listing_id)
    if not g.user.is_admin and listing.status != "Open" and listing.user_id != g.user.id: abort(404)
    return render_template("detail.html", kind="lost_found", title=f"{listing.item_type}: {listing.item_name}", subtitle=f"Listing #{listing.id} · {listing.category}",
                           record=listing, image=image_url(listing.image_filename))


@app.route("/lost-found/<int:listing_id>/edit", methods=["GET", "POST"])
@login_required
def lost_found_edit(listing_id):
    listing = db.get_or_404(LostFoundListing, listing_id)
    owner_or_admin(listing)
    if listing.status != "Open" and not g.user.is_admin: abort(403)
    if request.method == "POST" and save_lost_found(listing):
        flash("Listing updated.", "success")
        return redirect(url_for("lost_found_detail", listing_id=listing.id))
    return show_form("Edit listing", "Personal contact details are not shared through the public listing.", lost_found_fields(listing), url_for("lost_found_edit", listing_id=listing.id), "Save changes", True)


@app.post("/lost-found/<int:listing_id>/delete")
@login_required
def lost_found_delete(listing_id):
    listing = db.get_or_404(LostFoundListing, listing_id)
    owner_or_admin(listing)
    if g.user.is_admin:
        log_admin("listing_moderation_delete", "LostFoundListing", listing.id, f"Lost/found listing #{listing.id} was removed by an administrator.")
    db.session.delete(listing)
    db.session.commit()
    flash("Listing deleted.", "success")
    return redirect(url_for("lost_found_list"))


@app.post("/lost-found/<int:listing_id>/status")
@login_required
def lost_found_status(listing_id):
    listing = db.get_or_404(LostFoundListing, listing_id)
    owner_or_admin(listing)
    status = request.form.get("status", "")
    if status not in ["Open", "Resolved", "Returned"]:
        flash("Choose a valid status.", "danger")
    elif status == "Open" and not g.user.is_admin and listing.status != "Open":
        abort(403)
    else:
        listing.status = status
        if g.user.is_admin:
            log_admin("listing_moderation", "LostFoundListing", listing.id, f"Lost/found listing #{listing.id} marked {status}.")
        db.session.commit()
        flash("Listing status updated.", "success")
    return redirect(url_for("lost_found_detail", listing_id=listing.id))


# ---------------------------- G. RESOURCES -----------------------------
@app.route("/resources")
@login_required
def resource_list():
    query = ResourceListing.query if g.user.is_admin else ResourceListing.query.filter(ResourceListing.status == "Available")
    q = clean_text(request.args.get("q"), 100)
    category = request.args.get("category", "")
    listing_type = request.args.get("listing_type", "")
    if q: query = query.filter(or_(ResourceListing.title.ilike(f"%{q}%"), ResourceListing.description.ilike(f"%{q}%"), ResourceListing.subject.ilike(f"%{q}%")))
    if category in RESOURCE_CATEGORIES: query = query.filter_by(category=category)
    if listing_type in ["Offer", "Request"]: query = query.filter_by(listing_type=listing_type)
    listings = query.order_by(ResourceListing.created_at.desc()).limit(150).all()
    items = [list_item(f"{r.listing_type}: {r.title}", r.description[:160], r.status, f"{r.category}" + (f" · {r.subject}" if r.subject else "") + f" · {r.created_at:%d %b %Y}", url_for("resource_detail", resource_id=r.id)) for r in listings]
    return render_template("list.html", title="Resource Sharing", subtitle="Offer or request useful academic materials with other students.", items=items,
                           create_url=url_for("resource_create"), create_label="List a resource", empty_message="No resources match your filters.",
                           filters={"q": q, "category": category, "listing_type": listing_type}, categories=RESOURCE_CATEGORIES,
                           filter_kind="resources", type_options=["Offer", "Request"])


def resource_fields(resource=None):
    return [form_field("title", "Resource title", value=resource.title if resource else "", required=True),
            form_field("listing_type", "Listing type", "select", value=resource.listing_type if resource else "Offer", required=True, options=[("Offer", "Offer a resource"), ("Request", "Request a resource")]),
            form_field("category", "Category", "select", value=resource.category if resource else "Notes", required=True, options=[(x, x) for x in RESOURCE_CATEGORIES]),
            form_field("subject", "Subject or course (optional)", value=resource.subject if resource else ""),
            form_field("condition", "Physical book condition (optional)", "select", value=resource.condition if resource else "", options=[("", "Not applicable"), ("New", "New"), ("Good", "Good"), ("Used", "Used")]),
            form_field("description", "Description", "textarea", value=resource.description if resource else "", required=True)]


def save_resource(resource, is_new=False):
    title = clean_text(request.form.get("title"), 180)
    listing_type = request.form.get("listing_type", "")
    category = request.form.get("category", "")
    subject = clean_text(request.form.get("subject"), 100)
    condition = request.form.get("condition", "")
    description = clean_text(request.form.get("description"), 3000)
    errors = []
    if not title: errors.append("Resource title is required.")
    if listing_type not in ["Offer", "Request"]: errors.append("Choose Offer or Request.")
    if category not in RESOURCE_CATEGORIES: errors.append("Choose a valid category.")
    if condition not in ["", "New", "Good", "Used"]: errors.append("Choose a valid physical-book condition.")
    if len(description) < 5: errors.append("Description must contain at least 5 characters.")
    if errors:
        for error in errors: flash(error, "danger")
        return False
    resource.title, resource.listing_type, resource.category = title, listing_type, category
    resource.subject, resource.condition, resource.description = subject or None, condition or None, description
    if is_new:
        resource.user_id = g.user.id
        db.session.add(resource)
        db.session.flush()
    if g.user.is_admin:
        log_admin("resource_moderation", "ResourceListing", resource.id, f"Resource listing #{resource.id} was saved by an administrator.")
    db.session.commit()
    return True


@app.route("/resources/new", methods=["GET", "POST"])
@login_required
def resource_create():
    resource = ResourceListing()
    if request.method == "POST" and save_resource(resource, True):
        flash("Resource listing published.", "success")
        return redirect(url_for("resource_detail", resource_id=resource.id))
    return show_form("Create a resource listing", "Do not include personal contact details in your description.", resource_fields(), url_for("resource_create"), "Publish listing")


@app.route("/resources/<int:resource_id>")
@login_required
def resource_detail(resource_id):
    resource = db.get_or_404(ResourceListing, resource_id)
    if not g.user.is_admin and resource.status != "Available" and resource.user_id != g.user.id: abort(404)
    return render_template("detail.html", kind="resource", title=f"{resource.listing_type}: {resource.title}", subtitle=f"Resource #{resource.id} · {resource.category}", record=resource, image=None)


@app.route("/resources/<int:resource_id>/edit", methods=["GET", "POST"])
@login_required
def resource_edit(resource_id):
    resource = db.get_or_404(ResourceListing, resource_id)
    owner_or_admin(resource)
    if resource.status != "Available" and not g.user.is_admin: abort(403)
    if request.method == "POST" and save_resource(resource):
        flash("Resource listing updated.", "success")
        return redirect(url_for("resource_detail", resource_id=resource.id))
    return show_form("Edit resource listing", "Keep the description useful and safe for other students.", resource_fields(resource), url_for("resource_edit", resource_id=resource.id), "Save changes")


@app.post("/resources/<int:resource_id>/delete")
@login_required
def resource_delete(resource_id):
    resource = db.get_or_404(ResourceListing, resource_id)
    owner_or_admin(resource)
    if g.user.is_admin:
        log_admin("resource_moderation_delete", "ResourceListing", resource.id, f"Resource listing #{resource.id} was removed by an administrator.")
    db.session.delete(resource)
    db.session.commit()
    flash("Resource listing deleted.", "success")
    return redirect(url_for("resource_list"))


@app.post("/resources/<int:resource_id>/status")
@login_required
def resource_status(resource_id):
    resource = db.get_or_404(ResourceListing, resource_id)
    owner_or_admin(resource)
    status = request.form.get("status", "")
    if status not in ["Available", "Fulfilled", "Unavailable"]:
        flash("Choose a valid listing status.", "danger")
    elif status == "Available" and not g.user.is_admin and resource.status != "Available":
        abort(403)
    else:
        resource.status = status
        if g.user.is_admin:
            log_admin("resource_moderation", "ResourceListing", resource.id, f"Resource listing #{resource.id} marked {status}.")
        db.session.commit()
        flash("Resource status updated.", "success")
    return redirect(url_for("resource_detail", resource_id=resource.id))


# ---------------------------- H. ADMIN ANALYTICS -------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    counts = {
        "students": User.query.filter_by(role="student").count(),
        "ideas": Idea.query.count(),
        "ideas_review": Idea.query.filter(Idea.status.in_(["Submitted", "Under Review"])).count(),
        "ideas_approved_implemented": Idea.query.filter(Idea.status.in_(["Approved", "In Progress", "Implemented"])).count(),
        "feedback": Feedback.query.count(),
        "complaints": Complaint.query.count(),
        "complaints_pending": Complaint.query.filter_by(status="Pending").count(),
        "complaints_progress": Complaint.query.filter_by(status="In Progress").count(),
        "complaints_resolved": Complaint.query.filter_by(status="Resolved").count(),
        "active_polls": sum(1 for p in Poll.query.filter_by(status="Published").all() if p.current_state() == "Active"),
        "poll_votes": PollVote.query.count(),
        "notices": Notice.query.filter_by(status="Published").count(),
        "lost_found_open": LostFoundListing.query.filter_by(status="Open").count(),
        "resources_active": ResourceListing.query.filter_by(status="Available").count(),
    }
    avg_rating = db.session.query(func.avg(Feedback.rating)).scalar()
    counts["avg_rating"] = round(float(avg_rating), 2) if avg_rating is not None else 0

    def grouped_counts(model, column, order=None):
        query = db.session.query(column, func.count(model.id)).group_by(column)
        if order is not None:
            query = query.order_by(order)
        return query.all()

    complaint_cat = grouped_counts(Complaint, Complaint.category)
    complaint_status = grouped_counts(Complaint, Complaint.status)
    idea_status = grouped_counts(Idea, Idea.status)
    rating_by_category = db.session.query(Feedback.category, func.avg(Feedback.rating), func.count(Feedback.id)).group_by(Feedback.category).all()
    rating_distribution = db.session.query(Feedback.rating, func.count(Feedback.id)).group_by(Feedback.rating).order_by(Feedback.rating).all()
    popular_ideas = db.session.query(Idea.title, func.count(IdeaVote.id).label("votes")).outerjoin(IdeaVote).group_by(Idea.id).order_by(func.count(IdeaVote.id).desc()).limit(6).all()
    latest_poll = Poll.query.order_by(Poll.created_at.desc()).first()
    poll_labels, poll_values = [], []
    if latest_poll:
        poll_labels = [o.text for o in latest_poll.options]
        poll_values = [o.vote_count for o in latest_poll.options]
    charts = {
        "complaints_by_category": {"labels": [x[0] for x in complaint_cat], "values": [x[1] for x in complaint_cat]},
        "complaints_by_status": {"labels": [x[0] for x in complaint_status], "values": [x[1] for x in complaint_status]},
        "ideas_by_status": {"labels": [x[0] for x in idea_status], "values": [x[1] for x in idea_status]},
        "feedback_by_category": {"labels": [x[0] for x in rating_by_category], "values": [round(float(x[1]), 2) for x in rating_by_category]},
        "feedback_rating_distribution": {"labels": [f"{x[0]} star" for x in rating_distribution], "values": [x[1] for x in rating_distribution]},
        "popular_ideas": {"labels": [x[0][:30] for x in popular_ideas], "values": [x[1] for x in popular_ideas]},
        "latest_poll": {"title": latest_poll.question if latest_poll else "No polls yet", "labels": poll_labels, "values": poll_values},
    }
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(12).all()
    review_ideas = Idea.query.filter(Idea.status.in_(["Submitted", "Under Review"])).order_by(Idea.created_at.asc()).limit(5).all()
    open_complaints = Complaint.query.filter(Complaint.status.in_(["Pending", "In Progress"])).order_by(Complaint.created_at.asc()).limit(5).all()
    return render_template("admin_dashboard.html", counts=counts, charts=charts, logs=logs,
                           review_ideas=review_ideas, open_complaints=open_complaints)


@app.route("/my-activity")
@login_required
def my_activity():
    ideas = Idea.query.filter_by(user_id=g.user.id).order_by(Idea.created_at.desc()).limit(10).all()
    complaints = Complaint.query.filter_by(user_id=g.user.id).order_by(Complaint.created_at.desc()).limit(10).all()
    feedback = Feedback.query.filter_by(user_id=g.user.id).order_by(Feedback.created_at.desc()).limit(10).all()
    votes = IdeaVote.query.filter_by(user_id=g.user.id).order_by(IdeaVote.created_at.desc()).limit(10).all()
    poll_votes = PollVote.query.filter_by(user_id=g.user.id).order_by(PollVote.created_at.desc()).limit(10).all()
    return render_template("my_activity.html", ideas=ideas, complaints=complaints, feedback=feedback, votes=votes, poll_votes=poll_votes)


@app.cli.command("init-db")
def init_db_command():
    """Create missing database tables without clearing existing data."""
    db.create_all()
    click.echo("Database tables are ready. Existing records were not deleted.")


@app.cli.command("create-admin")
def create_admin_command():
    """Create the first or an additional administrator interactively."""
    name = click.prompt("Administrator name").strip()
    email = click.prompt("Administrator email").strip().lower()
    password = click.prompt("Administrator password", hide_input=True, confirmation_prompt=True)
    if len(name) < 2 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(password) < 12:
        raise click.ClickException("Use a valid name/email and a password of at least 12 characters.")
    if User.query.filter_by(email=email).first():
        raise click.ClickException("An account with this email already exists. The command will not silently promote an existing account.")
    user = User(name=name, email=email, role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f"Administrator account created for {email}.")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, title="Access denied", message="You do not have permission to view or change this record."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, title="Page not found", message="That page or record may not exist, or may not be available to your account."), 404


@app.errorhandler(CSRFError)
def csrf_error(_error):
    return render_template("error.html", code=400, title="Form expired", message="This form could not be verified. Reload the page and try again."), 400


@app.errorhandler(413)
def upload_too_large(_error):
    return render_template("error.html", code=413, title="Upload too large", message="The total upload must be no larger than 2 MB."), 413


@app.errorhandler(500)
def server_error(_error):
    db.session.rollback()
    return render_template("error.html", code=500, title="Something went wrong", message="The request could not be completed. Please try again."), 500


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
