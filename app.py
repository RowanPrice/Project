import time

from flask import Flask, jsonify, redirect, render_template, request, url_for

from pygame_controller import Game

app = Flask(__name__)
game = Game()
last_update = time.monotonic()


def update_game():
    global last_update
    now = time.monotonic()
    elapsed = now - last_update
    last_update = now
    game.update_enrichment(elapsed)


def state():
    centre = game.get_centre_status()
    enrichment = game.get_enrichment_status()
    reactor = game.get_status()
    return {
        "money": game.money,
        "mode": game_mode,
        "power_plant_on": game.power_plant_on,
        "reactor": reactor,
        "battery": {
            "charge": game.battery.current_charge,
            "capacity": game.battery.capacity,
            "mode": game.battery.mode,
            "rate_percentage": game.battery.rate_percentage
        },
        "science": {
            "enriched_fuel": centre["enriched_fuel"],
            "unenriched_fuel": centre["unenriched_fuel"],
            "enrichment_level": centre["enrichment_level"],
            "quality_level": centre["quality_level"],
            "speed_level": centre["speed_level"],
            "enrichment": enrichment,
            "upgrades": centre["upgrades"]
        }
    }


game_mode = "map"


@app.route("/")
def index():
    update_game()
    return render_template("index.html", data=state())


@app.post("/building/<building>")
def enter_building(building):
    global game_mode
    if building in ("power_plant", "science_centre"):
        game_mode = building
    return redirect(url_for("index"))


@app.post("/map")
def return_to_map():
    global game_mode
    game_mode = "map"
    return redirect(url_for("index"))


@app.route("/state")
def get_state():
    update_game()
    return jsonify(state())


@app.post("/mode/<mode>")
def set_mode(mode):
    global game_mode
    if mode in ("power_plant", "science_centre"):
        game_mode = mode
    return redirect(url_for("index"))


@app.post("/reactor/<action>")
def reactor_action(action):
    if not game.power_plant_on and action != "toggle":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(state())
        return redirect(url_for("index"))

    if action == "toggle":
        game.power_plant_on = not game.power_plant_on
        return redirect(url_for("index"))

    rod_values = request.form.getlist("rods")
    if not rod_values:
        rod_values = [request.form.get("rod", game.reactor.current_rod)]
    rod_indices = [int(value) for value in rod_values]
    if action == "select":
        if 0 <= rod_indices[0] < game.reactor.num_rods:
            game.reactor.current_rod = rod_indices[0]
    elif action == "raise":
        for rod_index in rod_indices:
            game.raise_rod(rod_index, 1)
    elif action == "lower":
        for rod_index in rod_indices:
            game.lower_rod(rod_index, 1)
    elif action == "scram":
        game.auto_scram()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        update_game()
        return jsonify(state())
    return redirect(url_for("index"))


@app.post("/science/buy-fuel")
def buy_fuel():
    amount = int(request.form.get("amount", 0))
    game.buy_unenriched_fuel(amount)
    return redirect(url_for("index"))


@app.post("/science/start-enrichment")
def start_enrichment():
    amount = int(request.form.get("amount", 0))
    percentage = float(request.form.get("percentage", 4.5))
    game.start_enrichment(amount, percentage)
    return redirect(url_for("index"))


@app.post("/science/skip-enrichment")
def skip_enrichment():
    game.skip_enrichment()
    return redirect(url_for("index"))


@app.post("/science/purchase-upgrade")
def purchase_upgrade():
    purchased = game.purchase_upgrade(
        request.form.get("category", ""),
        request.form.get("name", "")
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        update_game()
        response = state()
        response["purchase_succeeded"] = purchased
        return jsonify(response)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
