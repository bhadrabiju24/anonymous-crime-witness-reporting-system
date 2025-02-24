from flask_mysqldb import MySQL

mysql = MySQL()

def init_app(app):
    app.config['MYSQL_HOST'] = 'localhost'
    app.config['MYSQL_USER'] = 'root'
    app.config['MYSQL_PASSWORD'] = 'Bhadra@24'
    app.config['MYSQL_DB'] = 'anonymous_reporting_system'
    mysql.init_app(app)