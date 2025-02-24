from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory,jsonify
import os
import uuid
from werkzeug.utils import secure_filename
from flask_mysqldb import MySQL
from flask import session
import MySQLdb.cursors
import bcrypt
from textblob import TextBlob
from datetime import datetime


app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this in production

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '*******'
app.config['MYSQL_DB'] = 'anonymous_reporting_system'

mysql = MySQL(app)
def get_db_connection():
    return MySQLdb.connect(
        host="localhost",       # Change this if your database is hosted elsewhere
        user="root",       # Replace with your MySQL username
        password="*******",  # Replace with your MySQL password
        database="anonymous_reporting_system",  # Ensure this matches your database name
        cursorclass=MySQLdb.cursors.DictCursor
    )

def analyze_sentiment(text):
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    subjectivity = blob.sentiment.subjectivity
    return polarity, subjectivity


# File Upload Configuration
UPLOAD_FOLDER = 'uploads/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'mp4', 'mp3', 'wav', 'txt', 'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Function to check allowed file types
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Serve uploaded files
@app.route('/uploads/<path:filename>')
def serve_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def home():
    return render_template('home.html')

# ------------- USER REPORTING SYSTEM ---------------- #

FAKE_REPORT_KEYWORDS = ['churidhar', 'impossible', 'too perfect', 'unbelievable', 'unrealistic', 'unusual', 'strange']

def contains_fake_keywords(description):
    """Check if the description contains any keywords associated with fake reports."""
    description_lower = description.lower()
    return any(keyword in description_lower for keyword in FAKE_REPORT_KEYWORDS)

@app.route('/submit_report', methods=['GET', 'POST'])
def submit_report():
    if request.method == 'POST':
        description = request.form.get('description')
        date_str = request.form.get('date')
        location = request.form.get('location')
        files = request.files.getlist('evidence')

        # Check if the fields are filled
        if not description or not date_str or not location:
            flash("All fields are required.", "danger")
            return redirect(url_for('submit_report'))

        # Convert the submitted date to a datetime object
        try:
            submitted_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect(url_for('submit_report'))

        # Get the current date
        current_date = datetime.today()

        # Check if the submitted date is in the future
        if submitted_date > current_date:
            flash("The report date cannot be in the future.", "danger")
            return redirect(url_for('submit_report'))

        # Perform sentiment analysis
        polarity, subjectivity = analyze_sentiment(description)

        # Log sentiment for debugging
        print(f"Polarity: {polarity}, Subjectivity: {subjectivity}")

        # Flag report if sentiment is suspicious (fake report)
        if polarity < -0.5 and subjectivity > 0.7:
            flash("Report flagged as suspicious: Very negative and opinion-based.", "danger")
            return redirect(url_for('submit_report'))
        elif polarity > 0.5 and subjectivity > 0.7:
            flash("Report flagged as suspicious: Too positive and opinion-based.", "danger")
            return redirect(url_for('submit_report'))

        # Add check for fake keywords in the description
        if contains_fake_keywords(description):
            flash("Report flagged as suspicious: Contains unrealistic or unbelievable content.", "danger")
            return redirect(url_for('submit_report'))

        # Generate a unique report ID
        report_id = str(uuid.uuid4())
        file_paths = []
        
        # Save uploaded files (if any)
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                file_paths.append(filename)

        try:
            cursor = mysql.connection.cursor()
            cursor.execute(
                "INSERT INTO reports (report_id, description, date, location, status, polarity, subjectivity) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (report_id, description, date_str, location, "Pending", polarity, subjectivity)
            )

            for path in file_paths:
                cursor.execute("INSERT INTO media (report_id, file_path) VALUES (%s, %s)", (report_id, path))
            mysql.connection.commit()
            flash(f"Report submitted successfully! Your report ID is {report_id}.", "success")
        except Exception as e:
            mysql.connection.rollback()
            flash(f"An error occurred: {str(e)}", "danger")
        finally:
            cursor.close()

        return redirect(url_for('submit_report'))

    return render_template('submit_report.html')


@app.route('/check_status', methods=['GET', 'POST'])
def check_status():
    report = None
    media = None
    if request.method == 'POST':
        report_id = request.form.get('report_id')
        if not report_id:
            flash("Please provide a Report ID.", "danger")
            return redirect(url_for('check_status'))
        try:
            cursor = mysql.connection.cursor()
            cursor.execute("SELECT * FROM reports WHERE report_id = %s", (report_id,))
            report = cursor.fetchone()
            if report:
                cursor.execute("SELECT file_path FROM media WHERE report_id = %s", (report_id,))
                media = [row['file_path'] for row in cursor.fetchall()]
            else:
                flash("No report found with the provided ID.", "warning")
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "danger")
        finally:
            cursor.close()
    return render_template('check_status.html', report=report, media=media)

# ------------- ADMIN PANEL ---------------- #

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admins WHERE username = %s", (username,))
        admin = cursor.fetchone()
        conn.close()

        if admin and bcrypt.checkpw(password.encode('utf-8'), admin['password_hash'].encode('utf-8')):
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            return "Invalid credentials", 401

    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_logged_in' not in session or not session['admin_logged_in']:
        flash("Please log in to access the admin panel.", "warning")
        return redirect(url_for('admin_login'))

    cursor = mysql.connection.cursor()

    # Fetch all reports
    cursor.execute("SELECT * FROM reports")
    reports = cursor.fetchall()

    # Crime count by location
    cursor.execute("SELECT location, COUNT(*) FROM reports GROUP BY location")
    crime_by_location = cursor.fetchall()

    # Crime count by status
    cursor.execute("SELECT status, COUNT(*) FROM reports GROUP BY status")
    crime_by_status = cursor.fetchall()

    # Crime trends by date
    cursor.execute("SELECT DATE(created_at), COUNT(*) FROM reports GROUP BY DATE(created_at)")
    crime_by_date = cursor.fetchall()

    cursor.close()

    return render_template('admin_dashboard.html', reports=reports, 
                           crime_by_location=crime_by_location, 
                           crime_by_status=crime_by_status, 
                           crime_by_date=crime_by_date)


@app.route('/mark_fake_report/<string:report_id>', methods=['POST'])
def mark_fake_report(report_id):
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("UPDATE reports SET status = %s WHERE report_id = %s", ('Fake', report_id))
        mysql.connection.commit()
        cursor.close()
        return jsonify({'success': True, 'report_id': report_id})
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'success': False, 'error': str(e)})




@app.route('/admin/manage_reports')
def manage_reports():
    if 'admin_logged_in' not in session:
        flash("Please log in to access this feature.", "warning")
        return redirect(url_for('admin_login'))

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM reports")
    reports = cursor.fetchall()
    cursor.close()

    return render_template('manage_reports.html', reports=reports)



@app.route('/admin/update_status/<report_id>', methods=['GET', 'POST'])
def update_status(report_id):
    if 'admin_logged_in' not in session:
        flash("Please log in to access this feature.", "warning")
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        new_status = request.form.get('status')
        cursor = mysql.connection.cursor()
        cursor.execute("UPDATE reports SET status = %s WHERE report_id = %s", (new_status, report_id))
        mysql.connection.commit()
        cursor.close()
        flash("Report status updated successfully!", "success")
        return redirect(url_for('manage_reports'))

    return render_template('update_status.html', report_id=report_id)


@app.route('/request_witness/<report_id>', methods=['GET', 'POST'])
def request_witness(report_id):
    if request.method == 'POST':  # Ensure it's a POST request
        cursor = mysql.connection.cursor()
        
        # Update reminder_status instead of witness_requested
        cursor.execute("UPDATE reports SET reminder_status = 'Requested' WHERE report_id = %s", (report_id,))
        
        mysql.connection.commit()
        cursor.close()
        
        flash("Witness request sent successfully!", "success")
    
    return redirect(url_for('manage_reports'))



@app.route('/admin/delete_report/<report_id>')
def delete_report(report_id):
    if 'admin_logged_in' not in session:
        flash("Please log in to access this feature.", "warning")
        return redirect(url_for('admin_login'))

    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM reports WHERE report_id = %s", (report_id,))
    mysql.connection.commit()
    cursor.close()
    flash("Report deleted successfully!", "success")
    return redirect(url_for('manage_reports'))




@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("You have been logged out.", "info")
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))

# ------------- ERROR HANDLING ---------------- #
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True, port=8080)
