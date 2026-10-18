# CampusConnect — Project Synopsis

## 1. Project title
**CampusConnect — Smart College Improvement and Student Engagement Platform**

## 2. Problem statement
College communication about facilities, student suggestions, campus issues, notices, and learning resources is often spread across different channels. Students may not know whether a suggestion was reviewed or when a complaint was resolved. CampusConnect brings these activities into one web portal with a visible status workflow and role-based access.

## 3. Objectives
- Provide a central place for students to submit and track improvement ideas.
- Capture facility ratings and constructive feedback.
- Manage maintenance complaints through status changes and resolution notes.
- Support campus polls, notices/events, lost-and-found listings, and educational resource sharing.
- Give administrators database-backed statistics and an audit trail of important administrative actions.

## 4. Users
**Student:** registers, logs in, creates eligible submissions, votes, participates in polls, reads published notices, manages their own listings, and tracks their own private submissions.

**Administrator:** uses a protected dashboard to review suggestions and feedback, manage complaints and polls, publish notices, moderate listings, and view analytics/activity logs.

Public registration always creates a student account. The first administrator is created through Flask's command-line interface.

## 5. Scope and modules
1. Student Idea Hub and Idea-to-Action Tracker.
2. Feedback and Rating System.
3. Campus Complaint Management.
4. Campus Polls and Voting.
5. Digital Campus Notice Board.
6. Lost and Found.
7. Student Resource Sharing.
8. Administrative Analytics and Activity Logs.

## 6. Technology stack
- Frontend: HTML5, CSS3, JavaScript, Bootstrap 5, Bootstrap Icons, Chart.js.
- Backend: Python and Flask.
- Templates: Jinja2.
- Database: SQLite with SQLAlchemy ORM and foreign-key enforcement.
- Security: Werkzeug password hashing, server-side role/ownership checks, Flask-WTF CSRF protection, input validation, and safe image filenames.
- Testing: pytest.

Bootstrap, Bootstrap Icons, and Chart.js are referenced through CDNs. An internet connection is required for those external assets and charts; the application routes and database are local.

## 7. Architecture summary
The browser submits forms to Flask routes. Routes authenticate the session, validate server-side inputs and permissions, and call SQLAlchemy models. SQLAlchemy persists records to a SQLite database in the `instance` directory. Jinja templates render HTML responses. The administrator dashboard runs aggregate database queries and passes their results to Chart.js. Important administrator changes are recorded in `activity_logs`.

## 8. Core database tables
| Table | Purpose |
|---|---|
| `users` | Student and administrator accounts, role, and password hash |
| `ideas` | Improvement ideas, category, status, notes, optional image |
| `idea_votes` | Unique student vote for an idea |
| `feedback` | Private facility ratings/comments and admin response |
| `complaints` | Maintenance reports, location, priority, status, and notes |
| `polls` | Poll question, publication state, opening/closing time, visibility |
| `poll_options` | Available choices for each poll |
| `poll_votes` | One vote per student per poll |
| `notices` | Announcements, events, category, dates, URL, publication state |
| `lost_found_listings` | Lost/found entries and status |
| `resource_listings` | Educational resource offers and requests |
| `activity_logs` | Administrator ID, action, record, timestamp, and summary |

Primary keys, foreign keys, indexes, and uniqueness constraints are used where appropriate. Passwords are not stored in plain text. Student-facing routes check record ownership for private submissions.

## 9. Limitations and future improvements
- The project is designed for a local academic demonstration; a real college deployment needs HTTPS, a production secret key, backups, server monitoring, retention rules, and institutional review.
- Email notifications and direct messaging are intentionally not included.
- Image upload checks filenames/extensions and request size; production deployment could add content-based image verification and malware scanning.
- Charts use Chart.js from a CDN and need internet access to render.
- The interface uses straightforward Flask routes and server-rendered pages to keep the code understandable for a beginner.
