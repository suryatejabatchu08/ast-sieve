"""HTTP routes (control file: decorated route and main are entrypoints)."""
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


def main():
    app.run(port=8080)


if __name__ == "__main__":
    main()
