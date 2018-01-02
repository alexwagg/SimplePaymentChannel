from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, send_from_directory
import mysql.connector

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
	return render_template('home.html')







## for debugging purposes
if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0')