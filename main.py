import pygame

from Game.app import ChessApp


def main() -> None:
    app = ChessApp()
    try:
        app.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
