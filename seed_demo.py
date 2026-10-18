"""Optional demo data. Run explicitly with: python seed_demo.py

The script requires at least one registered student, creates only clearly marked
[DEMO] records that do not already exist, and never updates or deletes records.
"""
from datetime import datetime, timedelta

from app import app, db
from models import (
    Complaint, Feedback, Idea, IdeaVote, LostFoundListing, Notice,
    Poll, PollOption, PollVote, ResourceListing, User,
)


def seed_once(model, **lookup):
    return model.query.filter_by(**lookup).first()


with app.app_context():
    student = User.query.filter_by(role="student").order_by(User.id.asc()).first()
    if student is None:
        raise SystemExit("Create a student account in CampusConnect first, then run python seed_demo.py.")

    created = 0
    idea_specs = [
        ("[DEMO] Longer library hours", "Keep the library open later during internal and end-semester examinations.", "Library", "Under Review"),
        ("[DEMO] More charging points", "Add safe charging sockets near common study areas and waiting spaces.", "Classrooms", "Approved"),
        ("[DEMO] Better hostel Wi-Fi", "Check Wi-Fi access points on the hostel floors where signals are weak.", "Internet & Wi-Fi", "Submitted"),
    ]
    seeded_ideas = []
    for title, description, category, status in idea_specs:
        obj = seed_once(Idea, title=title)
        if not obj:
            obj = Idea(user_id=student.id, title=title, description=description, category=category, status=status,
                       admin_notes="[DEMO] Illustrative status note only." if status == "Approved" else None)
            db.session.add(obj)
            db.session.flush()
            created += 1
        seeded_ideas.append(obj)

    complaint_specs = [
        ("[DEMO] Classroom fan repair", "Electrical", "Block A, Room 12", "The ceiling fan makes noise and needs inspection.", "Pending", "Normal"),
        ("[DEMO] Water cooler service", "Water Supply", "Library ground floor", "The water cooler is not dispensing water consistently.", "In Progress", "High"),
    ]
    for title, category, location, desc, status, priority in complaint_specs:
        if not seed_once(Complaint, title=title):
            db.session.add(Complaint(user_id=student.id, title=title, category=category, location=location,
                                     description=desc, status=status, priority=priority))
            created += 1

    if not seed_once(Feedback, comment="[DEMO] The library is quiet and comfortable for study."):
        db.session.add(Feedback(user_id=student.id, category="Library", rating=4,
                                comment="[DEMO] The library is quiet and comfortable for study.", anonymous_display=True))
        created += 1

    now = datetime.now().replace(second=0, microsecond=0)
    if not seed_once(Poll, question="[DEMO] Which workshop should be organised next?"):
        poll = Poll(question="[DEMO] Which workshop should be organised next?",
                    description="Choose a topic you would like the college to host.",
                    opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=14),
                    status="Published", results_public=True)
        db.session.add(poll)
        db.session.flush()
        option1 = PollOption(poll_id=poll.id, text="AI and Data Science")
        option2 = PollOption(poll_id=poll.id, text="Cybersecurity basics")
        db.session.add_all([option1, option2])
        db.session.flush()
        # The unique (poll_id, user_id) constraint keeps demo voting consistent.
        db.session.add(PollVote(poll_id=poll.id, option_id=option1.id, user_id=student.id))
        created += 1

    if not seed_once(Notice, title="[DEMO] Student project showcase"):
        db.session.add(Notice(title="[DEMO] Student project showcase",
                              description="Students can showcase class projects and prototypes. Contact your faculty coordinator for details.",
                              category="Workshop", published_at=now, event_at=now + timedelta(days=10), status="Published"))
        created += 1
    if not seed_once(Notice, title="[DEMO] Internal assessment reminder"):
        db.session.add(Notice(title="[DEMO] Internal assessment reminder",
                              description="Review your subject schedule and confirm examination details with the department.",
                              category="Examination", published_at=now - timedelta(days=1), status="Published"))
        created += 1

    if not seed_once(LostFoundListing, item_name="[DEMO] Black umbrella"):
        db.session.add(LostFoundListing(user_id=student.id, item_name="[DEMO] Black umbrella", item_type="Found",
                                        category="Other", description="A black folding umbrella was found near the library entrance.",
                                        location="Library entrance", status="Open"))
        created += 1
    if not seed_once(ResourceListing, title="[DEMO] Data structures revision notes"):
        db.session.add(ResourceListing(user_id=student.id, title="[DEMO] Data structures revision notes",
                                       description="Revision notes covering arrays, linked lists, stacks, queues, and sorting.",
                                       category="Notes", listing_type="Offer", subject="Data Structures", status="Available"))
        created += 1
    if not seed_once(ResourceListing, title="[DEMO] Physics lab manual request"):
        db.session.add(ResourceListing(user_id=student.id, title="[DEMO] Physics lab manual request",
                                       description="Looking for a copy of the current semester physics laboratory manual.",
                                       category="Lab Manual", listing_type="Request", subject="Physics", status="Available"))
        created += 1

    db.session.commit()
    print(f"Demo setup complete. Added {created} new [DEMO] record(s); existing records were left unchanged.")
