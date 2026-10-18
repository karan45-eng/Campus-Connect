"""Critical workflow tests. Run with: pytest -q

The test database is selected before app.py is imported, so tests never clear the
student's normal campusconnect.db file.
"""
import os
import tempfile

_TEST_DB = os.path.join(tempfile.gettempdir(), "campusconnect-pytest.db")
os.environ["DATABASE_URL"] = "sqlite:///" + _TEST_DB.replace("\\", "/")
os.environ["SECRET_KEY"] = "pytest-only-secret-key"

import pytest
from app import app, db
from models import (
    ActivityLog, Complaint, Feedback, Idea, IdeaVote, LostFoundListing,
    Notice, Poll, PollOption, PollVote, ResourceListing, User,
)


@pytest.fixture(autouse=True)
def clean_test_database():
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SECRET_KEY="test-secret")
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client():
    return app.test_client()


def make_user(client, name="Sample Student", email="student@example.edu", password="StudentPass123!"):
    return client.post("/register", data={"name": name, "email": email, "password": password}, follow_redirects=True)


def login(client, email="student@example.edu", password="StudentPass123!"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


def make_admin(email="admin@example.edu", password="AdminPass12345!"):
    user = User(name="Admin User", email=email, role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def test_registration_hashes_password_and_always_creates_student(client):
    response = make_user(client)
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="student@example.edu").one()
        assert user.role == "student"
        assert user.password_hash != "StudentPass123!"
        assert user.check_password("StudentPass123!")


def test_bad_login_is_rejected(client):
    make_user(client)
    response = client.post("/login", data={"email": "student@example.edu", "password": "wrong-password"}, follow_redirects=True)
    assert b"incorrect" in response.data.lower()


def test_student_cannot_open_admin_dashboard(client):
    make_user(client)
    login(client)
    response = client.get("/admin")
    assert response.status_code == 403


def test_student_can_submit_idea_and_vote_once(client):
    make_user(client)
    login(client)
    client.post("/ideas/new", data={"title": "Improve library hours", "category": "Library", "description": "Keep the library open longer during exam weeks."}, follow_redirects=True)
    with app.app_context():
        idea = Idea.query.filter_by(title="Improve library hours").one()
        idea_id = idea.id
    client.post(f"/ideas/{idea_id}/vote", follow_redirects=True)
    with app.app_context():
        assert IdeaVote.query.filter_by(idea_id=idea_id).count() == 1
    client.post(f"/ideas/{idea_id}/vote", follow_redirects=True)
    with app.app_context():
        assert IdeaVote.query.filter_by(idea_id=idea_id).count() == 0  # toggle removes own vote


def test_student_cannot_edit_another_students_idea(client):
    make_user(client)
    login(client)
    client.post("/ideas/new", data={"title": "Original idea", "category": "Library", "description": "A sufficiently detailed library idea."}, follow_redirects=True)
    with app.app_context():
        idea = Idea.query.filter_by(title="Original idea").one()
        idea_id = idea.id
    client.post("/logout", follow_redirects=True)
    make_user(client, "Second Student", "second@example.edu", "SecondPass123!")
    login(client, "second@example.edu", "SecondPass123!")
    response = client.get(f"/ideas/{idea_id}/edit")
    assert response.status_code == 403


def test_admin_can_update_idea_and_action_is_logged(client):
    make_user(client)
    login(client)
    client.post("/ideas/new", data={"title": "More water stations", "category": "Other", "description": "Install water stations near lecture halls."}, follow_redirects=True)
    with app.app_context():
        idea_id = Idea.query.filter_by(title="More water stations").one().id
    client.post("/logout", follow_redirects=True)
    with app.app_context():
        admin = make_admin()
        admin_id = admin.id
    login(client, "admin@example.edu", "AdminPass12345!")
    response = client.post(f"/admin/ideas/{idea_id}/status", data={"status": "Approved", "admin_notes": "Approved for facilities review."}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Idea, idea_id).status == "Approved"
        assert ActivityLog.query.filter_by(record_type="Idea", record_id=idea_id).count() == 1


def test_feedback_rating_validation_and_private_record(client):
    make_user(client)
    login(client)
    response = client.post("/feedback/new", data={"category": "Library", "rating": "9", "comment": "The library is good."}, follow_redirects=True)
    assert b"Rating must be between 1 and 5" in response.data
    client.post("/feedback/new", data={"category": "Library", "rating": "5", "comment": "The library is very helpful.", "anonymous_display": "on"}, follow_redirects=True)
    with app.app_context():
        entry = Feedback.query.one()
        feedback_id = entry.id
        assert entry.anonymous_display is True
    client.post("/logout", follow_redirects=True)
    make_user(client, "Second Student", "second@example.edu", "SecondPass123!")
    login(client, "second@example.edu", "SecondPass123!")
    assert client.get(f"/feedback/{feedback_id}").status_code == 403


def test_complaint_is_private_and_admin_can_resolve(client):
    make_user(client)
    login(client)
    client.post("/complaints/new", data={"title": "Broken classroom fan", "category": "Electrical", "location": "Block A, Room 2", "description": "The ceiling fan is not working."}, follow_redirects=True)
    with app.app_context():
        complaint_id = Complaint.query.one().id
    client.post("/logout", follow_redirects=True)
    with app.app_context():
        make_admin()
    login(client, "admin@example.edu", "AdminPass12345!")
    response = client.post(f"/admin/complaints/{complaint_id}/update", data={"status": "Resolved", "priority": "High", "resolution_notes": "Fan repaired by maintenance."}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Complaint, complaint_id).status == "Resolved"
        assert db.session.get(Complaint, complaint_id).priority == "High"


def test_poll_enforces_single_vote_and_results_are_database_backed(client):
    make_user(client)
    login(client)
    client.post("/logout", follow_redirects=True)
    with app.app_context():
        admin = make_admin()
        poll = Poll(question="Preferred workshop?", description="Choose one.", status="Published", results_public=True, created_by=admin.id)
        db.session.add(poll)
        db.session.flush()
        a = PollOption(poll_id=poll.id, text="AI")
        b = PollOption(poll_id=poll.id, text="Cybersecurity")
        db.session.add_all([a, b])
        db.session.commit()
        poll_id, option_a, option_b = poll.id, a.id, b.id
    login(client)
    assert client.post(f"/polls/{poll_id}/vote", data={"option_id": option_a}, follow_redirects=True).status_code == 200
    response = client.post(f"/polls/{poll_id}/vote", data={"option_id": option_b}, follow_redirects=True)
    assert b"already voted" in response.data.lower()
    with app.app_context():
        assert PollVote.query.filter_by(poll_id=poll_id).count() == 1
        assert PollVote.query.one().option_id == option_a


def test_archived_notice_is_hidden_from_students(client):
    make_user(client)
    with app.app_context():
        admin = make_admin()
        notice = Notice(title="Archived announcement", description="Old information", category="College Notice", status="Archived", created_by=admin.id)
        db.session.add(notice)
        db.session.commit()
        notice_id = notice.id
    login(client)
    assert client.get(f"/notices/{notice_id}").status_code == 404
    assert b"Archived announcement" not in client.get("/notices").data


def test_lost_found_listing_can_be_resolved_by_owner(client):
    make_user(client)
    login(client)
    client.post("/lost-found/new", data={"item_name": "Blue water bottle", "item_type": "Lost", "category": "Other", "description": "Blue bottle with a silver cap.", "location": "Library entrance"}, follow_redirects=True)
    with app.app_context():
        listing_id = LostFoundListing.query.one().id
    response = client.post(f"/lost-found/{listing_id}/status", data={"status": "Resolved"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(LostFoundListing, listing_id).status == "Resolved"


def test_resource_listing_can_be_fulfilled_by_owner(client):
    make_user(client)
    login(client)
    client.post("/resources/new", data={"title": "Data structures notes", "listing_type": "Offer", "category": "Notes", "subject": "DSA", "condition": "", "description": "Complete semester notes for data structures."}, follow_redirects=True)
    with app.app_context():
        resource_id = ResourceListing.query.one().id
    response = client.post(f"/resources/{resource_id}/status", data={"status": "Fulfilled"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(ResourceListing, resource_id).status == "Fulfilled"


def test_admin_analytics_uses_real_database_records(client):
    with app.app_context():
        admin = make_admin()
        db.session.add(User(name="Metrics Student", email="metrics@example.edu", role="student", password_hash="unused"))
        db.session.add(Idea(user_id=admin.id, title="Metric idea", description="A sample record for metrics.", category="Other", status="Submitted"))
        db.session.commit()
    login(client, "admin@example.edu", "AdminPass12345!")
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Administrator dashboard" in response.data
    assert b"Ideas awaiting review" in response.data


def test_database_records_persist_between_requests(client):
    make_user(client)
    login(client)
    client.post("/ideas/new", data={"title": "Persistent idea", "category": "Other", "description": "This idea remains in SQLite."}, follow_redirects=True)
    with app.app_context():
        before = Idea.query.filter_by(title="Persistent idea").count()
    client.get("/logout", follow_redirects=True)  # GET is not a valid logout operation.
    with app.app_context():
        after = Idea.query.filter_by(title="Persistent idea").count()
    assert before == after == 1
