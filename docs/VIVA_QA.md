# CampusConnect — Viva Questions and Short Answers

### 1. What is CampusConnect?
CampusConnect is a web-based college improvement platform where students share ideas, rate facilities, report problems, vote in polls, view notices, and share learning resources.

### 2. Which problem does it solve?
It centralizes student engagement and makes the progress of ideas and complaints visible instead of leaving every activity in separate communication channels.

### 3. Which technologies are used?
Python, Flask, HTML, CSS, JavaScript, Bootstrap, Jinja2, SQLAlchemy, SQLite, Flask-WTF CSRF protection, and Chart.js.

### 4. What is Flask?
Flask is a lightweight Python web framework. It maps URL routes to Python functions and returns web responses.

### 5. What is SQLite?
SQLite is a relational database stored in a file. It is easy to set up for a small project because it does not require a separate database server.

### 6. What is SQLAlchemy?
SQLAlchemy is an object-relational mapper (ORM). It lets the project work with database rows through Python classes and objects.

### 7. What is a model?
A model is a Python class that represents a database table. For example, `Idea` represents improvement ideas and `IdeaVote` represents idea votes.

### 8. Why are there separate `Idea` and `IdeaVote` tables?
An idea can receive many votes, and each vote is associated with a student. A separate table lets the database enforce one vote per student per idea.

### 9. How is one vote per poll enforced?
The `poll_votes` table has a unique constraint on `(poll_id, user_id)`. The route also checks the poll's open status before saving a vote.

### 10. How are passwords stored?
Werkzeug generates a password hash. The original password is not stored, and login checks the entered password against that hash.

### 11. How does the application distinguish students from administrators?
Each user has a `role`. Decorators check login and administrator permissions on the server before protected routes run.

### 12. Why is server-side authorization important?
Hiding an admin button in the browser is not security. A person could manually request the URL, so the server must reject unauthorized access.

### 13. What is CSRF protection?
Cross-Site Request Forgery protection adds a token to forms and verifies that state-changing submissions originated from a valid application form.

### 14. What is the Idea-to-Action Tracker?
It records an official idea status such as Submitted, Under Review, Approved, In Progress, Implemented, or Rejected with notes.

### 15. How is anonymous feedback handled?
The anonymous-display setting prevents the author's name from being shown in public-facing displays. The account remains linked to the record for authorized administrator review, so it is not claimed to be absolutely anonymous.

### 16. How are administrator dashboard charts populated?
The dashboard runs aggregate queries against the SQLite database and passes the resulting labels and values to Chart.js. Chart values are not hardcoded.

### 17. What are foreign keys?
Foreign keys connect related records and help prevent invalid references, such as a vote pointing to an idea that does not exist. SQLite foreign-key enforcement is enabled for connections.

### 18. What is the purpose of the activity log?
It records important administrative changes, such as idea decisions, complaint updates, poll changes, and notice publication, to support traceability.

### 19. How do you run the project?
Create and activate a virtual environment, install `requirements.txt`, initialize the database, create an administrator account, and run `flask --app app.py run --debug`.

### 20. What would you improve before a real college deployment?
Use HTTPS and a strong secret key, establish backups and account policies, add institutional review and monitoring, test with real users, and add deployment-specific security controls.
