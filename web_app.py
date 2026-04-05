from flask import Flask, render_template, request, redirect, url_for
from pymongo import MongoClient
import certifi
from bson.objectid import ObjectId 

app = Flask(__name__)

# Setup Connection
ca = certifi.where()
uri = "mongodb+srv://joeanmarkhiolin_db_user:3vYbGdRiCncabJXs@cluster0.7vwb4kd.mongodb.net/"

try:
    client = MongoClient(uri, tlsCAFile=ca)
    db = client.sample_mflix
    movies_collection = db.movies
except Exception as e:
    print(f"Connection failed: {e}")
# READ: Display the page
@app.route('/')
def index():
    # Sort by '_id' descending to see the newest movies added first!
    movie_cursor = movies_collection.find({}, {"title": 1, "year": 1, "genres": 1}).sort("_id", -1).limit(20)
    movie_list = list(movie_cursor)
    return render_template('index.html', movies=movie_list)

# CREATE: Add a new movie
@app.route('/add', methods=['POST'])
def add_movie():
    title = request.form.get('title')
    year = request.form.get('year')
    genres_input = request.form.get('genres')
    
    # Convert comma-separated string into a proper Python list
    genres_list = [genre.strip() for genre in genres_input.split(',')]
    
    # Insert into MongoDB
    movies_collection.insert_one({
        "title": title,
        "year": int(year) if year.isdigit() else year,
        "genres": genres_list
    })
    
    # Refresh the page
    return redirect(url_for('index'))

# DELETE: Remove a movie
@app.route('/delete/<id>', methods=['POST'])
def delete_movie(id):
    # MongoDB uses a special ObjectId type for its _id fields
    movies_collection.delete_one({"_id": ObjectId(id)})
    
    # Refresh the page
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)