from flask import Flask, render_template
from pymongo import MongoClient
import certifi

app = Flask(__name__)

# 1. Setup Connection with SSL Certificate fix
# 'certifi.where()' provides the path to the certificate bundle required for Atlas
ca = certifi.where()
uri = "mongodb+srv://joeanmarkhiolin_db_user:3vYbGdRiCncabJXs@cluster0.7vwb4kd.mongodb.net/"

try:
    client = MongoClient(uri, tlsCAFile=ca)
    # Select the database and collection
    db = client.sample_mflix
    movies_collection = db.movies
    
    # Test connection
    client.admin.command('ping')
    print("Successfully connected to MongoDB!")
except Exception as e:
    print(f"Connection failed: {e}")

@app.route('/')
def index():
    # 2. Fetch data
    # We limit to 20 movies and only fetch fields we need for better performance
    movie_cursor = movies_collection.find({}, {"title": 1, "year": 1, "genres": 1}).limit(20)
    
    # Convert cursor to a list for the template
    movie_list = list(movie_cursor)
    
    return render_template('index.html', movies=movie_list)

if __name__ == '__main__':
    app.run(debug=True)