from flask import Flask
import json
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


@app.route("/")
def index():
    with open("data.json", "r") as file:
        data = json.load(file)
    # print(data)
    return data


if __name__ == "__main__":
    app.run(debug=True, port=5000)
