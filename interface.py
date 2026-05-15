import pygame
import time
from pygame_controller import Game
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
)

class GameGUI:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Nuclear Reactor")
        self.clock = pygame.time.Clock()

        self.game = Game()
        self.screen = pygame.display.set_mode([1200,750])
        self.background =


        self.running = True

    def main_loop(self):
        while self.running == True:
            self.handle_input()
            self.game.update_temperature()
            if self.game.update_temperature():
                self.game.auto_scram()
                break
            status = self.game.get_status()
            print(f"Temperature: {status['temperature']}°C, Average rod depth: {status['average_rod_depth']}")
            self.clock.tick(60)
            time.sleep(1)
        pygame.quit()

    def handle_input(self):
        key_count = 0
        for event in pygame.event.get():
            if event.type == KEYDOWN and event.key in [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]:
                for key in [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]:
                    if key == event.key:
                        if key_count <= self.game.game.num_rods:
                            self.game.game.current_rod = key_count
                    key_count += 1
            elif event.type == KEYDOWN and event.key == K_RIGHT and (self.game.game.current_rod+1) <= self.game.game.num_rods-1:
                self.game.game.current_rod += 1
            elif event.type == KEYDOWN and event.key == K_LEFT and (self.game.game.current_rod-1) >= 0:
                self.game.game.current_rod -= 1
            elif event.type == KEYDOWN and event.key == K_UP:
                self.game.raise_rod(self.game.game.current_rod, 10)
            elif event.type == KEYDOWN and event.key == K_DOWN:
                self.game.lower_rod(self.game.game.current_rod, 10)

    def draw(self):
        self.draw_reactor()

    def draw_reactor(self):
        pass


if __name__ == "__main__":
    gui = GameGUI()
    gui.main_loop()