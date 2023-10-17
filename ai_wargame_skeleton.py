from __future__ import annotations
import argparse
import copy
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from time import sleep
from typing import Tuple, TypeVar, Type, Iterable, ClassVar
import random
import requests

# maximum and minimum values for our heuristic scores (usually represents an end of game condition)
MAX_HEURISTIC_SCORE = 2000000000
MIN_HEURISTIC_SCORE = -2000000000


class UnitType(Enum):
    """Every unit type."""
    AI = 0
    Tech = 1
    Virus = 2
    Program = 3
    Firewall = 4


class ActionType(Enum):
    MOVE = 0
    ATTACK = 1
    REPAIR = 2
    SUICIDE = 3


class Player(Enum):
    """The 2 players."""
    Attacker = 0
    Defender = 1

    def next(self) -> Player:
        """The next (other) player."""
        if self is Player.Attacker:
            return Player.Defender
        else:
            return Player.Attacker


class GameType(Enum):
    AttackerVsDefender = 0
    AttackerVsComp = 1
    CompVsDefender = 2
    CompVsComp = 3


##############################################################################################################

@dataclass(slots=True)
class Unit:
    player: Player = Player.Attacker
    type: UnitType = UnitType.Program
    health: int = 9
    # class variable: damage table for units (based on the unit type constants in order)
    damage_table: ClassVar[list[list[int]]] = [
        [3, 3, 3, 3, 1],  # AI
        [1, 1, 6, 1, 1],  # Tech
        [9, 6, 1, 6, 1],  # Virus
        [3, 3, 3, 3, 1],  # Program
        [1, 1, 1, 1, 1],  # Firewall
    ]
    # class variable: repair table for units (based on the unit type constants in order)
    repair_table: ClassVar[list[list[int]]] = [
        [0, 1, 1, 0, 0],  # AI
        [3, 0, 0, 3, 3],  # Tech
        [0, 0, 0, 0, 0],  # Virus
        [0, 0, 0, 0, 0],  # Program
        [0, 0, 0, 0, 0],  # Firewall
    ]

    def is_alive(self) -> bool:
        """Are we alive ?"""
        return self.health > 0

    def mod_health(self, health_delta: int):
        """Modify this unit's health by delta amount."""
        self.health += health_delta
        if self.health < 0:
            self.health = 0
        elif self.health > 9:
            self.health = 9

    def to_string(self) -> str:
        """Text representation of this unit."""
        p = self.player.name.lower()[0]
        t = self.type.name.upper()[0]
        return f"{p}{t}{self.health}"

    def __str__(self) -> str:
        """Text representation of this unit."""
        return self.to_string()

    def damage_amount(self, target: Unit) -> int:
        """How much can this unit damage another unit."""
        amount = self.damage_table[self.type.value][target.type.value]
        if target.health - amount < 0:
            return target.health
        return amount

    def repair_amount(self, target: Unit) -> int:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        if target.health + amount > 9:
            return 9 - target.health
        return amount


##############################################################################################################

@dataclass(slots=True)
class Coord:
    """Representation of a game cell coordinate (row, col)."""
    row: int = 0
    col: int = 0

    def col_string(self) -> str:
        """Text representation of this Coord's column."""
        coord_char = '?'
        if self.col < 16:
            coord_char = "0123456789abcdef"[self.col]
        return str(coord_char)

    def row_string(self) -> str:
        """Text representation of this Coord's row."""
        coord_char = '?'
        if self.row < 26:
            coord_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[self.row]
        return str(coord_char)

    def to_string(self) -> str:
        """Text representation of this Coord."""
        return self.row_string() + self.col_string()

    def __str__(self) -> str:
        """Text representation of this Coord."""
        return self.to_string()

    def clone(self) -> Coord:
        """Clone a Coord."""
        return copy.copy(self)

    def iter_range(self, dist: int) -> Iterable[Coord]:
        """Iterates over Coords inside a rectangle centered on our Coord."""
        for row in range(self.row - dist, self.row + 1 + dist):
            for col in range(self.col - dist, self.col + 1 + dist):
                yield Coord(row, col)

    def iter_adjacent(self) -> Iterable[Coord]:
        """Iterates over adjacent Coords."""
        yield Coord(self.row - 1, self.col)
        yield Coord(self.row, self.col - 1)
        yield Coord(self.row + 1, self.col)
        yield Coord(self.row, self.col + 1)

    @classmethod
    def from_string(cls, s: str) -> Coord | None:
        """Create a Coord from a string. ex: D2."""
        s = s.strip()
        for sep in " ,.:;-_":
            s = s.replace(sep, "")
        if (len(s) == 2):
            coord = Coord()
            coord.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coord.col = "0123456789abcdef".find(s[1:2].lower())
            return coord
        else:
            return None


##############################################################################################################

@dataclass(slots=True)
class CoordPair:
    """Representation of a game move or a rectangular area via 2 Coords."""
    src: Coord = field(default_factory=Coord)
    dst: Coord = field(default_factory=Coord)

    def to_string(self) -> str:
        """Text representation of a CoordPair."""
        return self.src.to_string() + " " + self.dst.to_string()

    def __str__(self) -> str:
        """Text representation of a CoordPair."""
        return self.to_string()

    def clone(self) -> CoordPair:
        """Clones a CoordPair."""
        return copy.copy(self)

    def iter_rectangle(self) -> Iterable[Coord]:
        """Iterates over cells of a rectangular area."""
        for row in range(self.src.row, self.dst.row + 1):
            for col in range(self.src.col, self.dst.col + 1):
                yield Coord(row, col)

    @classmethod
    def from_quad(cls, row0: int, col0: int, row1: int, col1: int) -> CoordPair:
        """Create a CoordPair from 4 integers."""
        return CoordPair(Coord(row0, col0), Coord(row1, col1))

    @classmethod
    def from_dim(cls, dim: int) -> CoordPair:
        """Create a CoordPair based on a dim-sized rectangle."""
        return CoordPair(Coord(0, 0), Coord(dim - 1, dim - 1))

    @classmethod
    def from_string(cls, s: str) -> CoordPair | None:
        """Create a CoordPair from a string. ex: A3 B2"""
        s = s.strip()
        for sep in " ,.:;-_":
            s = s.replace(sep, "")
        if (len(s) == 4):
            coords = CoordPair()
            coords.src.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coords.src.col = "0123456789abcdef".find(s[1:2].lower())
            coords.dst.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[2:3].upper())
            coords.dst.col = "0123456789abcdef".find(s[3:4].lower())
            return coords
        else:
            return None


##############################################################################################################

@dataclass(slots=True)
class Options:
    """Representation of the game options."""
    dim: int = 5
    max_depth: int | None = 4
    min_depth: int | None = 2
    max_time: float | None = 5.0
    game_type: GameType = GameType.AttackerVsDefender
    alpha_beta: bool = False
    max_turns: int | None = 100
    randomize_moves: bool = True
    broker: str | None = None
    file = 'gametrace-' + str(alpha_beta) + '-' + str(max_time) + '-' + str(max_turns) + '.txt'


##############################################################################################################

@dataclass(slots=True)
class Stats:
    """Representation of the global game statistics."""
    evaluations_per_depth: dict[int, int] = field(default_factory=dict)
    total_seconds: float = 0.0


##############################################################################################################

@dataclass(slots=True)
class Game:
    """Representation of the game state."""
    board: list[list[Unit | None]] = field(default_factory=list)
    next_player: Player = Player.Attacker
    turns_played: int = 0
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai: bool = True
    _defender_has_ai: bool = True

    def __post_init__(self):
        """Automatically called after class init to set up the default board state."""
        dim = self.options.dim
        self.board = [[None for _ in range(dim)] for _ in range(dim)]
        md = dim - 1
        self.set(Coord(0, 0), Unit(player=Player.Defender, type=UnitType.AI))
        self.set(Coord(1, 0), Unit(player=Player.Defender, type=UnitType.Tech))
        self.set(Coord(0, 1), Unit(player=Player.Defender, type=UnitType.Tech))
        self.set(Coord(2, 0), Unit(player=Player.Defender, type=UnitType.Firewall))
        self.set(Coord(0, 2), Unit(player=Player.Defender, type=UnitType.Firewall))
        self.set(Coord(1, 1), Unit(player=Player.Defender, type=UnitType.Program))
        self.set(Coord(md, md), Unit(player=Player.Attacker, type=UnitType.AI))
        self.set(Coord(md - 1, md), Unit(player=Player.Attacker, type=UnitType.Virus))
        self.set(Coord(md, md - 1), Unit(player=Player.Attacker, type=UnitType.Virus))
        self.set(Coord(md - 2, md), Unit(player=Player.Attacker, type=UnitType.Program))
        self.set(Coord(md, md - 2), Unit(player=Player.Attacker, type=UnitType.Program))
        self.set(Coord(md - 1, md - 1), Unit(player=Player.Attacker, type=UnitType.Firewall))

    def clone(self) -> Game:
        """Make a new copy of a game for minimax recursion.

        Shallow copy of everything except the board (options and stats are shared).
        """
        new = copy.copy(self)
        new.board = copy.deepcopy(self.board)
        return new

    def is_empty(self, coord: Coord) -> bool:
        """Check if contents of a board cell of the game at Coord is empty (must be valid coord)."""
        return self.board[coord.row][coord.col] is None

    def get(self, coord: Coord) -> Unit | None:
        """Get contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            return self.board[coord.row][coord.col]
        else:
            return None

    def set(self, coord: Coord, unit: Unit | None):
        """Set contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            self.board[coord.row][coord.col] = unit

    def remove_dead(self, coord: Coord):
        """Remove unit at Coord if dead."""
        unit = self.get(coord)
        if unit is not None and not unit.is_alive():
            self.set(coord, None)
            if unit.type == UnitType.AI:
                if unit.player == Player.Attacker:
                    self._attacker_has_ai = False
                else:
                    self._defender_has_ai = False

    def mod_health(self, coord: Coord, health_delta: int):
        """Modify health of unit at Coord (positive or negative delta)."""
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)

    def is_valid_move(self, coords: CoordPair) -> bool:
        """Validate a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return False

        src_unit = self.get(coords.src)
        if src_unit is None or src_unit.player != self.next_player:
            return False

        if coords.src != coords.dst:
            for coord in coords.src.iter_adjacent():
                if coord == coords.dst:
                    dst_unit = self.get(coords.dst)
                    if dst_unit is not None:
                        action: ActionType = self.determine_action(coords)
                        if action == ActionType.REPAIR:
                            repair = src_unit.repair_table[src_unit.type.value][dst_unit.type.value]
                            if repair == 0:
                                return False
                            elif dst_unit.health == 9:
                                return False
                        return True
                    else:
                        return self.unit_movement_restriction(coords)
            return False
        else:
            return True

    def perform_move(self, coords: CoordPair) -> Tuple[bool, str]:
        """Validate and perform a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        if self.is_valid_move(coords):
            src_unit = self.get(coords.src)
            dst_unit = self.get(coords.dst)
            action: ActionType = self.determine_action(coords)

            if action == ActionType.MOVE:
                return self.perform_movement(coords)
            elif action == ActionType.ATTACK:
                return self.perform_attack(coords, src_unit, dst_unit)
            elif action == ActionType.REPAIR:
                return self.perform_repair(coords, src_unit, dst_unit)
            else:
                return self.perform_suicide(coords)
            return (True, "")

        return (False, "invalid move")

    def next_turn(self):
        """Transitions game to the next turn."""
        self.next_player = self.next_player.next()
        self.turns_played += 1

    def to_string(self) -> str:
        """Pretty text representation of the game."""
        dim = self.options.dim
        output = ""
        output += f"Next player: {self.next_player.name}\n"
        output += f"Turns played: {self.turns_played}\n"
        coord = Coord()
        output += "\n   "
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            output += f"{label:^3} "
        output += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            output += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    output += " .  "
                else:
                    output += f"{str(unit):^3} "
            output += "\n"
        return output

    def __str__(self) -> str:
        """Default string representation of a game."""
        return self.to_string()

    def is_valid_coord(self, coord: Coord) -> bool:
        """Check if a Coord is valid within out board dimensions."""
        dim = self.options.dim
        if coord.row < 0 or coord.row >= dim or coord.col < 0 or coord.col >= dim:
            return False
        return True

    def read_move(self) -> CoordPair:
        """Read a move from keyboard and return as a CoordPair."""
        while True:
            s = input(F'Player {self.next_player.name}, enter your move: ')
            coords = CoordPair.from_string(s)
            if coords is not None and self.is_valid_coord(coords.src) and self.is_valid_coord(coords.dst):
                return coords
            else:
                f = open(Options.file, "a")
                f.write('Invalid coordinates! Try again.\n')
                print('Invalid coordinates! Try again.')
                f.close()

    def human_turn(self):
        """Human player plays a move (or get via broker)."""
        if self.options.broker is not None:
            print("Getting next move with auto-retry from game broker...")
            while True:
                mv = self.get_move_from_broker()
                if mv is not None:
                    (success, result) = self.perform_move(mv)
                    print(f"Broker {self.next_player.name}: ", end='')
                    print(result)
                    if success:
                        # f = open(Options.file, "a")
                        # f.write(result)
                        # f.close()
                        self.next_turn()
                        break
                sleep(0.1)
        else:
            while True:
                mv = self.read_move()
                (success, result) = self.perform_move(mv)
                if success:
                    f = open(Options.file, "a")
                    f.write(result)
                    f.close()
                    print(f"Player {self.next_player.name}: ", end='')
                    print(result)
                    self.next_turn()
                    break
                else:
                    print("The move is not valid! Try again.")
                    f = open(Options.file, "a")
                    f.write("The move is not valid! Try again.\n")
                    f.close()

    def computer_turn(self) -> CoordPair | None:
        """Computer plays a move."""
        mv = self.suggest_move()
        if mv is not None:
            (success, result) = self.perform_move(mv)
            if success:
                f = open(Options.file, "a")
                f.write(result)
                f.close()
                print(f"Computer {self.next_player.name}: ", end='')
                print(result)
                self.next_turn()
        return mv

    def player_units(self, player: Player) -> Iterable[Tuple[Coord, Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord, unit)

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner"""
        if self.options.max_turns is not None and self.turns_played >= self.options.max_turns:
            return Player.Defender
        if self._attacker_has_ai:
            if self._defender_has_ai:
                return None
            else:
                return Player.Attacker
        return Player.Defender

    def move_candidates(self) -> Iterable[CoordPair]:
        """Generate valid move candidates for the next player."""
        move = CoordPair()
        for (src, _) in self.player_units(self.next_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move(move):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def calculate_heuristic3(self, move, action,prev_state) -> int:
        src_unit = prev_state.get(move.src)
        dst_unit = prev_state.get(move.dst)
        score = 1
        distance = 0

        if action == ActionType.MOVE:
            for coord in CoordPair.from_dim(prev_state.options.dim).iter_rectangle():
                unit = prev_state.get(coord)
                if unit is not None:
                    if unit.type == UnitType.AI and unit.player != src_unit.player:
                        distance = math.sqrt((coord.col - move.dst.col) ** 2 + (coord.row - move.dst.row) ** 2)
                        break

            if unit.type == UnitType.Virus:
                score = 80 - distance
            elif unit.type == UnitType.Firewall:
                score = 70 - distance
            elif unit.type == UnitType.Program:
                score = 60 - distance
            else:
                score = 50 - distance

            if src_unit.player == Player.Defender:
                score = score * -1

        elif action == ActionType.ATTACK:
            if src_unit.player == Player.Attacker:
                if src_unit.type == UnitType.Virus:
                    if dst_unit.type == UnitType.Tech:
                        score = 98
                    elif dst_unit.type == UnitType.Firewall:
                        score = 89
                    elif dst_unit.type == UnitType.Program:
                        score = 94
                    else:
                        score = 100
                elif src_unit.type == UnitType.Firewall:
                    if dst_unit.type == UnitType.Tech:
                        score = 92
                    elif dst_unit.type == UnitType.Firewall:
                        score = 91
                    elif dst_unit.type == UnitType.Program:
                        score = 93
                    else:
                        score = 90
                elif src_unit.type == UnitType.Program:
                    if dst_unit.type == UnitType.Tech:
                        score = 99
                    elif dst_unit.type == UnitType.Firewall:
                        score = 95
                    elif dst_unit.type == UnitType.Program:
                        score = 97
                    else:   # AI
                        score = 96
                else:
                    if dst_unit.type == UnitType.Tech:
                        score = 88
                    elif dst_unit.type == UnitType.Firewall:
                        score = 86
                    elif dst_unit.type == UnitType.Program:
                        score = 84
                    else:
                        score = 87
            else:
                if src_unit.type == UnitType.Tech:
                    if dst_unit.type == UnitType.Virus:
                        score = -91
                    elif dst_unit.type == UnitType.Firewall:
                        score = -86
                    elif dst_unit.type == UnitType.Program:
                        score = -92
                    else:
                        score = -93
                elif src_unit.type == UnitType.Firewall:
                    if dst_unit.type == UnitType.Virus:
                        score = -95
                    elif dst_unit.type == UnitType.Firewall:
                        score = -84
                    elif dst_unit.type == UnitType.Program:
                        score = -94
                    else:
                        score = -85
                elif src_unit.type == UnitType.Program:
                    if dst_unit.type == UnitType.Virus:
                        score = -83
                    elif dst_unit.type == UnitType.Firewall:
                        score = -87
                    elif dst_unit.type == UnitType.Program:
                        score = -96
                    else:
                        score = -97
                else:
                    if dst_unit.type == UnitType.Virus:
                        score = 0
                    elif dst_unit.type == UnitType.Firewall:
                        score = -81
                    elif dst_unit.type == UnitType.Program:
                        score = -80
                    else:
                        score = -79
        elif action == ActionType.REPAIR:
            if src_unit.player == Player.Attacker:
                score = 85
            else:
                if dst_unit.type == UnitType.Firewall:
                    if dst_unit.health <= 6:
                        score = -98
                    else:
                        score = -88

                elif dst_unit.type == UnitType.Program:
                    if dst_unit.health <= 6:
                        score = -99
                    else:
                        score = -89
                else:  # AI
                    if dst_unit.health <= 6:
                        score = -100
                    else:
                        score = -90

        else:
            # if dst_unit.type == UnitType.Firewall:
            #     score = 3
            # elif dst_unit.type == UnitType.Program:
            #     score = 2
            # elif dst_unit.type == UnitType.Virus or dst_unit.type == UnitType.Tech:
            #     score = 1
            # if not self.is_finished():
            #     score = 1
            # else:  # AI
            #     score = 0
            #
            # if self.next_player != Player.Defender:
            #     score = score * -1
            if self.next_player == Player.Attacker:
                score = 300
            else:
                score = -300
        return int(score)

    def calculate_heuristic2(self, move) -> int:
        VP1 = 0
        TP1 = 0
        FP1 = 0
        PP1 = 0
        AIP1 = 0
        VP2 = 0
        TP2 = 0
        FP2 = 0
        PP2 = 0
        AIP2 = 0

        # Iterate through the game board to count units for each player
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None:
                if unit.player == Player.Attacker:
                    if unit.type == UnitType.Virus:
                        VP1 += 1
                    elif unit.type == UnitType.Tech:
                        TP1 += 1
                    elif unit.type == UnitType.Firewall:
                        FP1 += 1
                    elif unit.type == UnitType.Program:
                        PP1 += 1
                    elif unit.type == UnitType.AI:
                        AIP1 += 1
                elif unit.player == Player.Defender:
                    if unit.type == UnitType.Virus:
                        VP2 += 1
                    elif unit.type == UnitType.Tech:
                        TP2 += 1
                    elif unit.type == UnitType.Firewall:
                        FP2 += 1
                    elif unit.type == UnitType.Program:
                        PP2 += 1
                    elif unit.type == UnitType.AI:
                        AIP2 += 1

        # Attacker matrices
        attacker_ai = [
            [-20, -15, -5, -5, -10],
            [-15, -10, -5, 10, -5],
            [-5, -5, -5, 15, 10],
            [-5, 10, 15, 20, 10],
            [-10, -5, 10, 10, 10]
        ]

        attacker_virus = [
            [10, 15, 15, 20, 15],
            [15, 10, 10, 15, 20],
            [15, 10, 10, 15, 15],
            [20, 15, 15, 10, 10],
            [15, 20, 15, 10, 10]
        ]

        attacker_program = [
            [-5, -5, 10, 15, 10],
            [-5, -5, 10, 15, 10],
            [-5, 10, 15, 0, 5],
            [10, 15, 10, 0, 0],
            [0, 0, 5, 0, 0]
        ]

        attacker_firewall = [
            [-10, -10, -5, -5, 0],
            [-10, -10, 15, 15, 0],
            [-5, 15, 15, 10, 0],
            [-5, 15, 10, 5, 0],
            [0, 0, 0, 0, 0]
        ]

        # Defender matrices
        defender_ai = [
            [10, 5, 0, -5, -20],
            [5, 5, 0, -5, -20],
            [0, 0, 0, -5, -20],
            [-5, -5, -5, -5, -20],
            [-20, -20, -20, -20, -20]
        ]

        defender_tech = [
            [10, 10, 10, 5, -5],
            [10, 15, 15, 0, -10],
            [10, 15, 0, -10, -20],
            [5, 0, -10, -20, -20],
            [-5, -10, -20, -20, -20]
        ]

        defender_program = [
            [0, 0, 0, 0, 0],
            [0, 5, 10, 5, -10],
            [0, 10, 5, -5, -20],
            [0, 5, -5, -20, -20],
            [0, -10, -20, -20, -20]
        ]

        defender_firewall = [
            [0, 0, 5, 10, -5],
            [0, 0, 10, 5, -10],
            [5, 10, 5, -10, -20],
            [10, 5, -10, -20, -20],
            [-5, -10, -20, -20, -20]
        ]

        unit = self.get(move.dst)
        score = 1

        if unit is not None:
            if unit.player == Player.Attacker:
                if unit.type == UnitType.Virus:
                    score = attacker_virus[move.dst.col][move.dst.row]
                elif unit.type == UnitType.Firewall:
                    score = attacker_firewall[move.dst.col][move.dst.row]
                elif unit.type == UnitType.Program:
                    score = attacker_program[move.dst.col][move.dst.row]
                elif unit.type == UnitType.AI:
                    score = attacker_ai[move.dst.col][move.dst.row]
            elif unit.player == Player.Defender:
                if unit.type == UnitType.Tech:
                    score = defender_tech[move.dst.col][move.dst.row]
                elif unit.type == UnitType.Firewall:
                    score = defender_firewall[move.dst.col][move.dst.row]
                elif unit.type == UnitType.Program:
                    score = defender_program[move.dst.col][move.dst.row]
                elif unit.type == UnitType.AI:
                    score = defender_ai[move.dst.col][move.dst.row]

        # Calculate the heuristic score based on the provided formula
        heuristic_score = (
                (10 * VP1 + 8 * TP1 + 3 * FP1 + 3 * PP1 + 999 * AIP1) -
                (10 * VP2 + 8 * TP2 + 3 * FP2 + 3 * PP2 + 999 * AIP2)
        ) * score

        return heuristic_score

    def calculate_heuristic(self) -> int:
        VP1 = 0
        TP1 = 0
        FP1 = 0
        PP1 = 0
        AIP1 = 0
        VP2 = 0
        TP2 = 0
        FP2 = 0
        PP2 = 0
        AIP2 = 0

        # Iterate through the game board to count units for each player
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None:
                if unit.player == Player.Attacker:
                    if unit.type == UnitType.Virus:
                        VP1 += 1
                    elif unit.type == UnitType.Firewall:
                        FP1 += 1
                    elif unit.type == UnitType.Program:
                        PP1 += 1
                    elif unit.type == UnitType.AI:
                        AIP1 += 1
                elif unit.player == Player.Defender:
                    if unit.type == UnitType.Tech:
                        TP2 += 1
                    elif unit.type == UnitType.Firewall:
                        FP2 += 1
                    elif unit.type == UnitType.Program:
                        PP2 += 1
                    elif unit.type == UnitType.AI:
                        AIP2 += 1

        # Calculate the heuristic score based on the provided formula
        heuristic_score = (
                (3 * VP1 + 3 * TP1 + 3 * FP1 + 3 * PP1 + 9999 * AIP1) -
                (3 * VP2 + 3 * TP2 + 3 * FP2 + 3 * PP2 + 9999 * AIP2)
        )

        return heuristic_score

    def minimax(self, depth, maximizing_player, alpha, beta, start_time, move, action,prev_state):
        if depth == 0 or self.is_finished():
            return self.calculate_heuristic3(move, action,prev_state), None, 0  # Also return the best move

        if maximizing_player:
            max_eval = MIN_HEURISTIC_SCORE
            best_move = None  # Initialize the best move
            possible_moves = list(self.move_candidates())
            for move in possible_moves:
                if self.options.max_time is not None:
                    if (datetime.now() - start_time).total_seconds() >= self.options.max_time:
                        # Time limit exceeded, return the last result
                        break
                game_clone = self.clone()
                action2 = self.determine_action(move)
                game_clone.perform_move(move)
                game_clone.next_turn()
                eval, _, _ = game_clone.minimax(depth - 1, False, alpha, beta, start_time, move, action2,self.clone())
                if eval > max_eval:
                    max_eval = eval
                    best_move = move  # Update the best move
                if self.options.alpha_beta:
                    alpha = max(alpha, eval)
                    if beta <= alpha:
                        break
            best_result = (max_eval, best_move, depth)
            return best_result
        else:
            min_eval = MAX_HEURISTIC_SCORE
            best_move = None  # Initialize the best move
            possible_moves = list(self.move_candidates())
            for move in possible_moves:
                if self.options.max_time is not None:
                    if (datetime.now() - start_time).total_seconds() >= self.options.max_time:
                        # Time limit exceeded, return the last result
                        break
                game_clone = self.clone()
                action2 = self.determine_action(move)
                game_clone.perform_move(move)
                game_clone.next_turn()
                eval, _, _ = game_clone.minimax(depth - 1, True, alpha, beta, start_time, move, action2,self.clone())
                if eval < min_eval:
                    min_eval = eval
                    best_move = move  # Update the best move
                if self.options.alpha_beta:
                    beta = min(beta, eval)
                    if beta <= alpha:
                        break

            return min_eval, best_move, 0

    def random_move(self) -> Tuple[int, CoordPair | None, float]:
        """Returns a random move."""
        move_candidates = list(self.move_candidates())
        random.shuffle(move_candidates)
        if len(move_candidates) > 0:
            return (0, move_candidates[0], 1)
        else:
            return (0, None, 0)

    def suggest_move(self) -> CoordPair | None:
        """Suggest the next move using minimax alpha beta. TODO: REPLACE RANDOM_MOVE WITH PROPER GAME LOGIC!!!"""
        start_time = datetime.now()
        game_clone = self.clone()
        if self.next_player == Player.Attacker:
            (score, move, avg_depth) = game_clone.minimax(2, True, MIN_HEURISTIC_SCORE, MAX_HEURISTIC_SCORE, start_time,
                                                          None, None,None)
        else:
            (score, move, avg_depth) = game_clone.minimax(2, False, MIN_HEURISTIC_SCORE, MAX_HEURISTIC_SCORE,
                                                          start_time, None, None,None)

        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        self.stats.total_seconds += elapsed_seconds
        print(f"Heuristic score: {score}")
        print(f"Average recursive depth: {avg_depth:0.1f}")
        print(f"Evals per depth: ", end='')
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}:{self.stats.evaluations_per_depth[k]} ", end='')
        print()
        total_evals = sum(self.stats.evaluations_per_depth.values())
        if self.stats.total_seconds > 0:
            print(f"Eval perf.: {total_evals / self.stats.total_seconds / 1000:0.1f}k/s")
        print(f"Elapsed time: {elapsed_seconds:0.1f}s")
        return move

    def post_move_to_broker(self, move: CoordPair):
        """Send a move to the game broker."""
        if self.options.broker is None:
            return
        data = {
            "from": {"row": move.src.row, "col": move.src.col},
            "to": {"row": move.dst.row, "col": move.dst.col},
            "turn": self.turns_played
        }
        try:
            r = requests.post(self.options.broker, json=data)
            if r.status_code == 200 and r.json()['success'] and r.json()['data'] == data:
                # print(f"Sent move to broker: {move}")
                pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")

    def get_move_from_broker(self) -> CoordPair | None:
        """Get a move from the game broker."""
        if self.options.broker is None:
            return None
        headers = {'Accept': 'application/json'}
        try:
            r = requests.get(self.options.broker, headers=headers)
            if r.status_code == 200 and r.json()['success']:
                data = r.json()['data']
                if data is not None:
                    if data['turn'] == self.turns_played + 1:
                        move = CoordPair(
                            Coord(data['from']['row'], data['from']['col']),
                            Coord(data['to']['row'], data['to']['col'])
                        )
                        print(f"Got move from broker: {move}")
                        return move
                    else:
                        # print("Got broker data for wrong turn.")
                        # print(f"Wanted {self.turns_played+1}, got {data['turn']}")
                        pass
                else:
                    # print("Got no data from broker")
                    pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")
        return None

    def determine_action(self, coords: CoordPair) -> ActionType:
        src_unit = self.get(coords.src)
        dst_unit = self.get(coords.dst)
        if coords.src == coords.dst:
            return ActionType.SUICIDE
        else:
            if dst_unit is None:
                return ActionType.MOVE
            else:
                if src_unit.player == dst_unit.player:
                    return ActionType.REPAIR
                else:
                    return ActionType.ATTACK

    def perform_attack(self, coords: CoordPair, src_unit: Unit, dst_unit: Unit) -> Tuple[bool, str]:
        src_damage = src_unit.damage_table[src_unit.type.value][dst_unit.type.value] * -1
        dst_damage = src_unit.damage_table[dst_unit.type.value][src_unit.type.value] * -1
        self.mod_health(coords.src, src_damage)
        self.mod_health(coords.dst, dst_damage)
        return (True, 'attack from ' + str(coords.src) + ' to ' + str(coords.dst) + '\n' +
                'combat damage to source = ' + str(src_damage * -1) + ' , to target = ' + str(dst_damage * -1))

    def perform_repair(self, coords: CoordPair, src_unit: Unit, dst_unit: Unit) -> Tuple[bool, str]:
        repair = src_unit.repair_table[src_unit.type.value][dst_unit.type.value]
        self.mod_health(coords.dst, repair)
        return (True, 'repair from ' + str(coords.src) + ' to ' + str(coords.dst) + '\n' +
                "repaired " + str(repair) + ' health point')

    def perform_movement(self, coords: CoordPair) -> Tuple[bool, str]:
        self.set(coords.dst, self.get(coords.src))
        self.set(coords.src, None)
        return (True, 'move from ' + str(coords.src) + ' to ' + str(coords.dst))

    def perform_suicide(self, coords: CoordPair) -> Tuple[bool, str]:
        self.mod_health(coords.src, -9)
        # Loop through all elements in the rectangular area of coords.src
        total_damage = 0
        for coord in coords.src.iter_range(1):
            if self.get(coord) is not None:
                self.mod_health(coord, -2)
                total_damage += 2
        return (True, "self-destruct at " + str(coords.src) + ' and deals ' + str(total_damage) + ' total damage')

    def unit_movement_restriction(self, coords: CoordPair) -> bool:
        src_unit = self.get(coords.src)

        row_dst = coords.dst.row - coords.src.row
        col_dst = coords.dst.col - coords.src.col

        # AI, Firewall and program move restrictions
        if src_unit.type in [UnitType.AI, UnitType.Firewall, UnitType.Program]:
            if src_unit.player == Player.Attacker:
                if row_dst > 0 or col_dst > 0:
                    return False
            else:
                if row_dst < 0 or col_dst < 0:
                    return False

            # Checks if the Player 1 Unit is adjacent to Player 2 Unit
            for coord in coords.src.iter_adjacent():
                unit = self.get(coord)
                if unit is not None:
                    if src_unit.type in [UnitType.AI, UnitType.Firewall, UnitType.Program] \
                            and src_unit.player != unit.player:
                        return False
        return True


##############################################################################################################

def main():
    # parse command line arguments
    parser = argparse.ArgumentParser(
        prog='ai_wargame',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--max_depth', type=int, help='maximum search depth')
    parser.add_argument('--max_time', type=float, help='maximum search time')
    parser.add_argument('--game_type', type=str, default="auto", help='game type: auto|attacker|defender|manual')
    parser.add_argument('--broker', type=str, help='play via a game broker')
    args = parser.parse_args()

    # parse the game type
    if args.game_type == "attacker":
        game_type = GameType.AttackerVsComp
    elif args.game_type == "defender":
        game_type = GameType.CompVsDefender
    elif args.game_type == "manual":
        game_type = GameType.AttackerVsDefender
    else:
        game_type = GameType.CompVsComp

    # set up game options
    options = Options(
        dim=5,  # int
        max_depth=4,  # int | None
        min_depth=2,  # int | None
        max_time=None,  # float | None
        game_type=game_type,  # GameType
        alpha_beta=False,  # bool
        max_turns=200,  # int | None
        randomize_moves=True,  # bool
        broker=None  # str | None
    )

    # override class defaults via command line options
    if args.max_depth is not None:
        options.max_depth = args.max_depth
    if args.max_time is not None:
        options.max_time = args.max_time
    if args.broker is not None:
        options.broker = args.broker

    # create a new game
    game = Game(options=options)
    # the main game loop

    f = open(Options.file, "w")
    f.write('Game set to ' + str(options.max_turns) + ' turns \n')
    f.write('Game set to ' + str(options.max_time) + ' sec per turn \n')
    f.write(str(options.game_type)[9:] + '\n')
    f.write("alpha-beta is " + str(options.alpha_beta) + "\n")
    while True:
        print()
        print(game)

        f = open(Options.file, "a")
        f.write(str(game))
        f.close()
        winner = game.has_winner()
        if winner is not None:
            print(f"{winner.name} wins in " + str(game.turns_played) + " turns")
            f = open(Options.file, "a")
            f.write(f"{winner.name} wins in " + str(game.turns_played) + " turns")
            f.close()
            break
        if game.options.game_type == GameType.AttackerVsDefender:
            game.human_turn()
        elif game.options.game_type == GameType.AttackerVsComp and game.next_player == Player.Attacker:
            game.human_turn()
        elif game.options.game_type == GameType.CompVsDefender and game.next_player == Player.Defender:
            game.human_turn()
        else:
            player = game.next_player
            move = game.computer_turn()
            if move is not None:
                game.post_move_to_broker(move)
            else:
                print("Computer doesn't know what to do!!!")
                exit(1)


##############################################################################################################

if __name__ == '__main__':
    main()
