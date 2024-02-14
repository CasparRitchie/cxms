from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    # Serve the index.html file
    return render_template('index.html')

@app.route('/style-guide')
def style_guide():
    # Serve the style-guide.html file
    return render_template('style-guide.html')

if __name__ == "__main__":
    # Run the application
    app.run(debug=True)
