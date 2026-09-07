import pygame
import flask
import time
from controller import Game
from pygame.locals import (
    K_0,
    K_1,
    K_2,
    K_3,
    K_4,
    K_5,
    K_6,
    K_7,
    K_8,
    K_9,
    K_UP,
    K_DOWN,
    K_LEFT,
    K_RIGHT,
    KEYDOWN,
    QUIT,
    FULLSCREEN,
    K_ESCAPE,
    K_p,
    K_s,
    K_h,
    K_RETURN,
    K_BACKSPACE
)

class GameGUI:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Nuclear Reactor")
        self.clock = pygame.time.Clock()

        self.game = Game()
        self.screen = pygame.display.set_mode([1200,750])
        #self.background =
        
        self.mode = "power_plant"  # Default mode: "power_plant" or "science_centre"
        self.show_updates = True
        self.upgrade_options = []
        self.selected_upgrade = 0
        self.upgrade_buttons = []
        self.science_tab = "upgrades"
        self.enrichment_tab_button = pygame.Rect(35, 70, 250, 36)
        self.upgrades_tab_button = pygame.Rect(300, 70, 250, 36)
        self.start_enrichment_button = pygame.Rect(100, 350, 170, 45)
        self.skip_enrichment_button = pygame.Rect(1010, 700, 155, 32)
        self.centrifuge_placeholder = pygame.Rect(760, 150, 400, 500)
        self.fuel_plus_button = pygame.Rect(310, 181, 30, 28)
        self.batch_decrease_button = pygame.Rect(55, 350, 35, 45)
        self.batch_increase_button = pygame.Rect(275, 350, 40, 45)
        self.show_fuel_shop = False
        self.fuel_shop_buttons = []
        self.fuel_shop_panel = pygame.Rect(300, 210, 390, 290)
        self.fuel_shop_buy_button = pygame.Rect(330, 400, 330, 40)
        self.fuel_shop_cancel_button = pygame.Rect(330, 450, 330, 34)
        self.fuel_amount_input = "100"
        self.selected_batch_amount = 100
        self.title_font = pygame.font.Font(None, 42)
        self.font = pygame.font.Font(None, 25)
        self.small_font = pygame.font.Font(None, 21)

        self.running = True

    def main_loop(self):
        self.display_controls()
        while self.running == True:
            self.handle_input()
            self.game.update_enrichment(1)
            self.game.update_temperature()
            if self.game.update_temperature():
                self.game.auto_scram()
                break
            status = self.game.get_status()
            if self.show_updates:
                print(f"Temperature: {status['temperature']}°C, Average rod depth: {status['average_rod_depth']}")
            self.draw()
            pygame.display.flip()
            self.clock.tick(60)
            time.sleep(1)
        pygame.quit()

    def display_controls(self):
        print("\n=== Nuclear Reactor Controls ===")
        print("P        Switch to Power Plant mode")
        print("S        Switch to Science Centre mode")
        print("0-4      Select a control rod")
        print("H        Show/hide temperature updates")
        print("Left/Right  Select the previous or next rod")
        print("Up       Raise the selected rod")
        print("Down     Lower the selected rod")
        print("Escape   Exit the program")
        print("================================\n")

    def handle_input(self):
        key_count = 0
        for event in pygame.event.get():
            # Mode switching
            if event.type == KEYDOWN and event.key == K_p:
                self.mode = "power_plant"
                self.show_updates = True
                print("Switched to Power Plant control mode")
            elif event.type == KEYDOWN and event.key == K_s:
                self.mode = "science_centre"
                self.show_updates = False
                self.science_tab = "upgrades"
                print("Switched to Science Centre control mode")
                self.display_upgrade_menu()
            elif event.type == KEYDOWN and event.key == K_h:
                if self.mode == "power_plant":
                    self.show_updates = not self.show_updates
                    state = "shown" if self.show_updates else "hidden"
                    print(f"Temperature updates {state}")
            
            # Power plant controls (only active in power_plant mode)
            elif self.mode == "power_plant":
                if event.type == KEYDOWN and event.key in [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]:
                    for key in [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]:
                        if key == event.key:
                            if key_count <= self.game.reactor.num_rods:
                                self.game.reactor.current_rod = key_count
                        key_count += 1
                elif event.type == KEYDOWN and event.key == K_RIGHT and (self.game.reactor.current_rod+1) <= self.game.reactor.num_rods-1:
                    self.game.reactor.current_rod += 1
                elif event.type == KEYDOWN and event.key == K_LEFT and (self.game.reactor.current_rod-1) >= 0:
                    self.game.reactor.current_rod -= 1
                elif event.type == KEYDOWN and event.key == K_UP:
                    self.game.raise_rod(self.game.reactor.current_rod, 10)
                elif event.type == KEYDOWN and event.key == K_DOWN:
                    self.game.lower_rod(self.game.reactor.current_rod, 10)
                elif event.type == KEYDOWN and event.key == K_9:
                    self.game.scram()

            # Science Centre controls (only active in science_centre mode)
            elif self.mode == "science_centre":
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.show_fuel_shop:
                    if self.fuel_shop_buy_button.collidepoint(event.pos):
                        self.buy_fuel_from_input()
                    elif self.fuel_shop_cancel_button.collidepoint(event.pos):
                        self.show_fuel_shop = False
                    elif not self.fuel_shop_panel.collidepoint(event.pos):
                        self.show_fuel_shop = False
                elif event.type == KEYDOWN and self.show_fuel_shop:
                    if event.key == K_BACKSPACE:
                        self.fuel_amount_input = self.fuel_amount_input[:-1]
                    elif event.key == K_RETURN:
                        self.buy_fuel_from_input()
                    elif event.unicode.isdigit() and len(self.fuel_amount_input) < 6:
                        self.fuel_amount_input += event.unicode
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.enrichment_tab_button.collidepoint(event.pos):
                    self.science_tab = "enrichment"
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.upgrades_tab_button.collidepoint(event.pos):
                    self.science_tab = "upgrades"
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.science_tab == "upgrades":
                    for index, button in enumerate(self.upgrade_buttons):
                        if button.collidepoint(event.pos):
                            self.selected_upgrade = index
                            self.purchase_selected_upgrade()
                            break
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.science_tab == "enrichment":
                    if self.fuel_plus_button.collidepoint(event.pos):
                        self.show_fuel_shop = True
                    elif self.batch_decrease_button.collidepoint(event.pos) and not self.game.enrichment_in_progress:
                        self.selected_batch_amount = max(0, self.selected_batch_amount - 10)
                    elif self.batch_increase_button.collidepoint(event.pos) and not self.game.enrichment_in_progress:
                        maximum = self.game.science_centre.unenriched_fuel
                        self.selected_batch_amount = min(maximum, self.selected_batch_amount + 10)
                    elif self.start_enrichment_button.collidepoint(event.pos):
                        if self.game.start_enrichment(self.selected_batch_amount):
                            print("Enrichment started")
                    elif self.skip_enrichment_button.collidepoint(event.pos):
                        if self.game.skip_enrichment():
                            print("Developer skip: enrichment completed")
                elif event.type == KEYDOWN and event.key == K_UP and self.science_tab == "upgrades":
                    if self.upgrade_options:
                        self.selected_upgrade = (self.selected_upgrade - 1) % len(self.upgrade_options)
                        self.display_upgrade_menu()
                elif event.type == KEYDOWN and event.key == K_DOWN and self.science_tab == "upgrades":
                    if self.upgrade_options:
                        self.selected_upgrade = (self.selected_upgrade + 1) % len(self.upgrade_options)
                        self.display_upgrade_menu()
                elif event.type == KEYDOWN and event.key == K_RETURN and self.science_tab == "upgrades":
                    self.purchase_selected_upgrade()
            
            # Exit (works in any mode)
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                self.running = False

    def draw(self):
        self.screen.fill((24, 30, 38))
        self.draw_money()
        if self.mode == "science_centre":
            self.draw_science_centre()
        else:
            self.draw_reactor()

    def draw_money(self):
        money_text = self.font.render(f"Money: £{self.game.money:,}", True, (247, 211, 92))
        money_position = money_text.get_rect(topright=(1160, 25))
        self.screen.blit(money_text, money_position)

    def draw_reactor(self):
        title = self.title_font.render("Nuclear Reactor - Power Plant", True, (235, 240, 245))
        self.screen.blit(title, (35, 30))
        status = self.game.get_status()
        lines = [
            f"Temperature: {status['temperature']} C",
            f"Average rod depth: {status['average_rod_depth']}",
            f"Selected rod: {self.game.reactor.current_rod}"
        ]
        for index, line in enumerate(lines):
            text = self.font.render(line, True, (210, 218, 226))
            self.screen.blit(text, (40, 105 + index * 35))

    def draw_science_centre(self):
        title = self.title_font.render("Science Centre", True, (235, 240, 245))
        self.screen.blit(title, (35, 25))

        self.draw_science_tabs()
        if self.science_tab == "enrichment":
            self.draw_enrichment_panel()
            return

        headers = [(40, "Category"), (205, "Upgrade"), (470, "Effect"), (800, "Cost"), (930, "Action")]
        for x_position, header in headers:
            text = self.font.render(header, True, (137, 211, 196))
            self.screen.blit(text, (x_position, 118))

        self.upgrade_buttons = []
        row_height = 40
        for index, (category, upgrade_name, upgrade) in enumerate(self.upgrade_options):
            y_position = 142 + index * row_height
            row_colour = (42, 52, 63) if index % 2 == 0 else (35, 44, 54)
            if index == self.selected_upgrade:
                row_colour = (55, 77, 82)
            pygame.draw.rect(self.screen, row_colour, (25, y_position, 1145, row_height - 2))

            values = [category, upgrade_name, upgrade["effect"], f"£{upgrade['cost']}"]
            positions = [40, 205, 470, 800]
            for x_position, value in zip(positions, values):
                text = self.small_font.render(value, True, (225, 230, 235))
                self.screen.blit(text, (x_position, y_position + 10))

            button = pygame.Rect(930, y_position + 5, 175, 28)
            self.upgrade_buttons.append(button)
            if upgrade["purchased"]:
                button_colour = (90, 96, 102)
                button_text = "Purchased"
            elif self.game.money < upgrade["cost"]:
                button_colour = (190, 65, 65)
                button_text = "Not enough money"
            else:
                button_colour = (52, 161, 125)
                button_text = "Purchase"
            pygame.draw.rect(self.screen, button_colour, button, border_radius=4)
            text = self.small_font.render(button_text, True, (255, 255, 255))
            text_position = text.get_rect(center=button.center)
            self.screen.blit(text, text_position)

        footer = self.small_font.render("Click Purchase, or use Up/Down and Enter. Press P to return.", True, (180, 190, 200))
        self.screen.blit(footer, (35, 705))

    def draw_science_tabs(self):
        for button, label, tab_name in (
            (self.enrichment_tab_button, "Enrichment", "enrichment"),
            (self.upgrades_tab_button, "Purchase Upgrades", "upgrades")
        ):
            colour = (52, 161, 125) if self.science_tab == tab_name else (70, 82, 94)
            pygame.draw.rect(self.screen, colour, button, border_radius=4)
            text = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(text, text.get_rect(center=button.center))

    def draw_enrichment_panel(self):
        status = self.game.get_centre_status()
        enrichment_status = self.game.get_enrichment_status()
        if not enrichment_status["in_progress"]:
            self.selected_batch_amount = min(
                self.selected_batch_amount,
                status["unenriched_fuel"]
            )
        lines = [
            f"Enriched fuel: {status['enriched_fuel']} units",
            f"Unenriched fuel: {status['unenriched_fuel']} units",
            f"Enrichment level: {status['enrichment_level']:.2f}%",
            f"Centrifuge quality: level {status['quality_level']} ({status['enrichment_multiplier']}x)",
            f"Centrifuge speed: level {status['speed_level']} ({status['speed_multiplier']}x)"
        ]
        for index, line in enumerate(lines):
            text = self.font.render(line, True, (225, 230, 235))
            self.screen.blit(text, (55, 145 + index * 38))

        pygame.draw.rect(self.screen, (52, 161, 125), self.fuel_plus_button, border_radius=4)
        plus_text = self.font.render("+", True, (255, 255, 255))
        self.screen.blit(plus_text, plus_text.get_rect(center=self.fuel_plus_button.center))

        if enrichment_status["in_progress"]:
            progress = enrichment_status["progress"]
            progress_text = f"Enrichment progress: {progress * 100:.1f}%"
            time_text = f"Time remaining: {enrichment_status['time_left']:.0f} seconds"
            pygame.draw.rect(self.screen, (55, 65, 75), (55, 340, 520, 24), border_radius=4)
            pygame.draw.rect(self.screen, (52, 161, 125), (55, 340, int(520 * progress), 24), border_radius=4)
            self.screen.blit(self.font.render(progress_text, True, (225, 230, 235)), (55, 280))
            self.screen.blit(self.font.render(time_text, True, (225, 230, 235)), (55, 310))
            button_text = "Enrichment running"
            button_colour = (90, 96, 102)
        else:
            self.screen.blit(self.font.render(f"Ready to enrich {self.selected_batch_amount} units at 4.5%.", True, (225, 230, 235)), (55, 280))
            button_text = "Start Enrichment"
            button_colour = (52, 161, 125) if self.selected_batch_amount > 0 else (90, 96, 102)

        if not enrichment_status["in_progress"]:
            pygame.draw.rect(self.screen, (70, 82, 94), self.batch_decrease_button, border_radius=4)
            pygame.draw.rect(self.screen, (70, 82, 94), self.batch_increase_button, border_radius=4)
            self.screen.blit(self.font.render("-", True, (255, 255, 255)), (68, 361))
            self.screen.blit(self.font.render("+", True, (255, 255, 255)), (289, 361))

        pygame.draw.rect(self.screen, button_colour, self.start_enrichment_button, border_radius=4)
        start_text = self.font.render(button_text, True, (255, 255, 255))
        self.screen.blit(start_text, start_text.get_rect(center=self.start_enrichment_button.center))

        pygame.draw.rect(self.screen, (82, 88, 96), self.centrifuge_placeholder, border_radius=4)
        placeholder_text = self.font.render("Centrifuge sprite placeholder", True, (210, 215, 220))
        self.screen.blit(placeholder_text, placeholder_text.get_rect(center=self.centrifuge_placeholder.center))

        pygame.draw.rect(self.screen, (120, 75, 55), self.skip_enrichment_button, border_radius=4)
        skip_text = self.small_font.render("DEV: Skip wait", True, (255, 255, 255))
        self.screen.blit(skip_text, skip_text.get_rect(center=self.skip_enrichment_button.center))
        self.upgrade_buttons = []
        if self.show_fuel_shop:
            self.draw_fuel_shop()

    def draw_fuel_shop(self):
        pygame.draw.rect(self.screen, (38, 47, 57), self.fuel_shop_panel, border_radius=6)
        pygame.draw.rect(self.screen, (90, 105, 118), self.fuel_shop_panel, 2, border_radius=6)
        title = self.font.render("Buy Unenriched Fuel", True, (235, 240, 245))
        self.screen.blit(title, (325, 230))
        input_box = pygame.Rect(330, 275, 330, 40)
        pygame.draw.rect(self.screen, (24, 30, 38), input_box, border_radius=4)
        input_text = self.font.render(self.fuel_amount_input or "0", True, (255, 255, 255))
        self.screen.blit(input_text, (345, 283))
        price = int(self.fuel_amount_input or 0) * self.game.fuel_price
        price_text = self.small_font.render(f"Cost: £{price:,}", True, (210, 218, 226))
        self.screen.blit(price_text, (330, 325))

        affordable = price > 0 and self.game.money >= price
        button_colour = (52, 161, 125) if affordable else (190, 65, 65)
        pygame.draw.rect(self.screen, button_colour, self.fuel_shop_buy_button, border_radius=4)
        buy_text = self.small_font.render("Buy fuel", True, (255, 255, 255))
        self.screen.blit(buy_text, buy_text.get_rect(center=self.fuel_shop_buy_button.center))

        pygame.draw.rect(self.screen, (70, 82, 94), self.fuel_shop_cancel_button, border_radius=4)
        cancel_text = self.small_font.render("Cancel", True, (255, 255, 255))
        self.screen.blit(cancel_text, cancel_text.get_rect(center=self.fuel_shop_cancel_button.center))

    def buy_fuel_from_input(self):
        amount = int(self.fuel_amount_input or 0)
        if self.game.buy_unenriched_fuel(amount):
            print(f"Bought {amount} units of unenriched fuel")
            self.selected_batch_amount = min(amount, self.game.science_centre.unenriched_fuel)
            self.show_fuel_shop = False
        else:
            print("Not enough money or invalid fuel amount")

    def display_upgrade_menu(self):
        self.upgrade_options = []
        upgrades = self.game.science_centre.upgrades
        for category, category_upgrades in upgrades.items():
            for upgrade_name, upgrade in category_upgrades.items():
                self.upgrade_options.append((category, upgrade_name, upgrade))

        if self.upgrade_options:
            self.selected_upgrade %= len(self.upgrade_options)
        else:
            self.selected_upgrade = 0


    def purchase_selected_upgrade(self):
        if not self.upgrade_options:
            return

        category, upgrade_name, upgrade = self.upgrade_options[self.selected_upgrade]
        if not upgrade["purchased"]:
            self.game.purchase_upgrade(category, upgrade_name)
            self.display_upgrade_menu()


if __name__ == "__main__":
    gui = GameGUI()
    gui.main_loop()