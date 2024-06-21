"""Optimized version of game.py."""
import copy
import numpy as np

from bridge import players
from pb import alphabridge_pb2
import fastgame

import pdb


MODE_DEBUG = 'python'
MODE_FAST = 'c'


def _named_vector_position(n, doc=None):
    def getter(self):
        value = self._vector[n]
        if value == -1:
            return None
        else:
            return value

    def setter(self, value):
        if value is None:
            self._vector[n] = -1
        else:
            self._vector[n] = value

    return property(getter, setter, None, doc)


class DealState:
    def __init__(self, dealer=None, dealt_cards=0, min_length=0, max_length=13):
        self._vector = np.zeros(330, dtype=np.int8)
        self.dealt_cards[:] = dealt_cards
        self.min_length[:] = min_length
        self.max_length[:] = max_length
        self.played_cards[:] = 0
        self.first_to_mention[:] = 0
        self.tricks_taken[:] = 0
        self.stage = None if dealer == None else self.STAGE_BIDDING
        self.next_to_act = dealer
        self.pass_position = 0
        self.last_bid_seat = None
        self.last_bid_level = None
        self.last_bid_strain = None
        self.last_bid_double = None
        self.declarer = None
        self.trick_suit = None
        self.trick_position = None
        self.trick_winning_seat = None
        self.trick_winning_suit = None
        self.trick_winning_rank = None
        self.bidding_is_open = 0

    @property
    def dealt_cards(self):
        return np.reshape(self._vector[:208], (4, 4, 13))

    @property
    def played_cards(self):
        return np.reshape(self._vector[208:260], (4, 13))

    @property
    def min_length(self):
        return np.reshape(self._vector[260:276], (4, 4))

    @property
    def max_length(self):
        return np.reshape(self._vector[276:292], (4, 4))

    @property
    def first_to_mention(self):
        return np.reshape(self._vector[292:312], (4, 5))

    @property
    def tricks_taken(self):
        return np.reshape(self._vector[312:316], (4))

    stage = _named_vector_position(316 + 0)
    next_to_act = _named_vector_position(316 + 1)
    pass_position = _named_vector_position(316 + 2)
    last_bid_seat = _named_vector_position(316 + 3)
    last_bid_level = _named_vector_position(316 + 4)
    last_bid_strain = _named_vector_position(316 + 5)
    last_bid_double = _named_vector_position(316 + 6)
    declarer = _named_vector_position(316 + 7)
    trick_suit = _named_vector_position(316 + 8)
    trick_position = _named_vector_position(316 + 9)
    trick_winning_seat = _named_vector_position(316 + 10)
    trick_winning_suit = _named_vector_position(316 + 11)
    trick_winning_rank = _named_vector_position(316 + 12)
    bidding_is_open = _named_vector_position(316 + 13)

    STAGE_BIDDING = 0
    STAGE_PLAY = 1
    STAGE_SCORING = 2
    STAGE_ERROR = 3
    CALL_PASS = 0
    CALL_DOUBLE = 1
    CALL_REDOUBLE = 2

    def dummy_is_public(self):
        return self.trick_position or self.tricks_taken.sum() != 0

    def add_cards(self, seat, cards):
        for cards_seat in range(4):
            if seat is None or cards_seat == seat:
                self.dealt_cards[cards_seat,:,:] |= cards[cards_seat,:,:]
                for suit in range(4):
                    n = self.dealt_cards[cards_seat,suit,:].sum()
                    if n > self.min_length[cards_seat,suit]:
                        self.min_length[cards_seat,suit] = n

    def give_card(self, seat, suit, rank):
        if self.stage == self.STAGE_ERROR:
            return
        if self.dealt_cards[:,suit,rank].sum() > 0:
            self.set_error("Duplicate card")
        elif self.played_cards[suit, rank] > 0:
            self.set_error("Card already played")
        elif self.dealt_cards[seat,:,:].sum() >= 13:
            self.set_error("14 cards in hand")
        elif self.dealt_cards[seat,suit,:].sum() >= self.min_length[seat,suit]:
            self.min_length[seat,suit] += 1
            if self.min_length[seat,suit] > self.max_length[seat,suit]:
                self.set_error("Revoke?")
            else:
                self.dealt_cards[seat,suit,rank] = 1
        else:
            self.dealt_cards[seat,suit,rank] = 1

    def set_error(self, msg):
        if self.stage != self.STAGE_ERROR:
            self.stage = self.STAGE_ERROR
            self.error_message = msg

    def execute_action_ids(self, ids, history):
        raise NotImplementedError


class DebugDealState(DealState):
# TODO(njt): uncomment ater a) needed and (b) tested.
#    def shrink_lengths(self):
#        min_length = self.min_length
#        max_length = self.max_length
#
#        for seat in range(4):
#            for suit in range(4):
#                n = self.dealt_cards[seat,suit,:].sum()
#                if n > min_length[seat,suit]:
#                    min_length[seat,suit] = n
#
#        dirty = True
#        while dirty:
#            dirty = False
#            for seat in range(4):
#                for suit in range(4):
#                    n = min_length[seat,:].sum()
#                    n -= min_length[seat,suit]
#                    if 13 - n < max_length[seat,suit]:
#                        max_length[seat,suit] = 13 - n
#                        dirty = True
#
#                    n = min_length[:,suit].sum()
#                    n -= min_length[seat,suit]
#                    if 13 - n < max_length[seat,suit]:
#                        max_length[seat,suit] = 13 - n
#                        dirty = True
#
#                    n = max_length[seat,:].sum()
#                    n -= max_length[seat,suit]
#                    if 13 - n > min_length[seat,suit]:
#                        min_length[seat,suit] = 13 - n
#                        dirty = True
#
#                    n = max_length[:,suit].sum()
#                    n -= max_length[seat,suit]
#                    if 13 - n > min_length[seat,suit]:
#                        min_length[seat,suit] = 13 - n
#                        dirty = True
#
#                    if min_length[seat,suit] > max_length[seat,suit]:
#                        raise ValueError

    def execute_action_ids(self, ids, history):
        for i, action_id in enumerate(ids):
            if self.stage == self.STAGE_ERROR:
                return i
            elif self.stage == self.STAGE_SCORING:
                self.set_error("action after deal finished")
                return i
            history[i, :] = (self.next_to_act, action_id)
            if action_id < 35:
                level_ix = action_id // 5
                strain_ix = action_id % 5
                self._execute_bid_action(level_ix, strain_ix)
            elif action_id < 38:
                self._execute_call_action(action_id - 35)
            else:
                suit_ix = (action_id - 38) // 13
                rank_ix = (action_id - 38) % 13
                self._execute_play_action(suit_ix, rank_ix)
            
        return len(ids)

    def _execute_bid_action(self, level_ix, strain_ix):
        if not self._check_equal(
                self.stage, self.STAGE_BIDDING, "stage for bid"):
            return
        if self.last_bid_level is not None:
            if level_ix < self.last_bid_level or (
                    level_ix == self.last_bid_level and
                    strain_ix <= self.last_bid_strain):
                self.set_error("Insufficient bid")
                return
        self.last_bid_seat = self.next_to_act
        self.last_bid_level = level_ix
        self.last_bid_strain = strain_ix
        self.last_bid_double = 0
        partner_seat = (self.next_to_act + 2) % 4
        if not self.first_to_mention[partner_seat, strain_ix]:
            self.first_to_mention[self.next_to_act, strain_ix] = 1
        self.pass_position = 0
        self.next_to_act = (self.next_to_act + 1) % 4

    def _execute_call_action(self, call):
        if not self._check_equal(
                self.stage, self.STAGE_BIDDING, "stage for call"):
            return
        if call == self.CALL_PASS:  # PASS
            if self.pass_position == 3:
                self.stage = self.STAGE_SCORING
                self.next_to_act = None
                self.pass_position = 0
            elif self.last_bid_level is not None and self.pass_position == 2:
                self.stage = self.STAGE_PLAY
                self.pass_position = None
                self.trick_position = 0
                if self.first_to_mention[self.last_bid_seat,self.last_bid_strain]:
                    self.declarer = self.last_bid_seat
                else:
                    self.declarer = (self.last_bid_seat + 2) % 4
                self.next_to_act = (self.declarer + 1) % 4
            else:
                self.pass_position += 1
                self.next_to_act = (self.next_to_act + 1) % 4
        elif call == self.CALL_DOUBLE:
            if not self._check_equal(
                    self.last_bid_double, 0, "double state for double"):
                pass
            elif self.last_bid_seat % 2 == self.next_to_act % 2:
                self.set_error("double of own sides' contract")
            else:
                self.last_bid_double = 1
                self.pass_position = 0
                self.next_to_act = (self.next_to_act + 1) % 4
        elif call == self.CALL_REDOUBLE:
            if not self._check_equal(
                    self.last_bid_double, 1, "double state for redouble"):
                pass
            elif self.last_bid_seat % 2 != self.next_to_act % 2:
                self.set_error("redouble of other sides' contract")
            else:
                self.last_bid_double = 2
                self.pass_position = 0
                self.next_to_act = (self.next_to_act + 1) % 4

    def _is_strongest_card_played(self, suit, rank):
        trump = self.last_bid_strain
        if suit == trump and self.trick_winning_suit != trump:
            return True
        if suit != self.trick_winning_suit:
            return False
        return rank > self.trick_winning_rank


    def _execute_play_action(self, suit, rank):
        if not self._check_equal(
                self.stage, self.STAGE_PLAY, "stage for play"):
            return
        seat = self.next_to_act
        if self.played_cards[suit, rank]:
            self.set_error("Card already played")
        if (self.trick_position != 0 and suit != self.trick_suit and
                (self.dealt_cards[seat,self.trick_suit,:] &
                ~self.played_cards[self.trick_suit]).sum() > 0):
            self.set_error("Revoke")
        if self.trick_position != 0 and suit != self.trick_suit:
            self.max_length[seat, self.trick_suit] = \
                    self.min_length[seat, self.trick_suit]
        if not self.dealt_cards[seat, suit, rank]:
            self.give_card(seat, suit, rank)
        if self.stage == self.STAGE_ERROR:
            return

        self.played_cards[suit, rank] = 1
        if self.trick_position == 0:
            self.trick_suit = suit

        if self.trick_position == 0 or self._is_strongest_card_played(
                suit, rank):
            self.trick_winning_seat = seat
            self.trick_winning_suit = suit
            self.trick_winning_rank = rank

        if self.trick_position < 3:
            self.trick_position += 1
            self.next_to_act = (self.next_to_act + 1) % 4
        else:
            self.trick_position = 0
            self.next_to_act = self.trick_winning_seat
            self.tricks_taken[self.trick_winning_seat] += 1
            if self.tricks_taken.sum() == 13:
                self.stage = self.STAGE_SCORING 
                self.next_to_act = None

    def _check_equal(self, actual, expected, context):
        if actual == expected:
            return True
        else:
            self.set_error(f"{context}: {actual} != {expected}")
            return False

class FastDealState(DealState):
    def execute_action_ids(self, ids, history):
        if self.stage != self.STAGE_ERROR:
            n, err = fastgame.execute_action_ids(self._vector, ids, history)
            if self.stage == self.STAGE_ERROR:
                self.error_message = err
            return n
        else:
            return 0


class Game:
    def __init__(self, num_ranks=13, mode=MODE_FAST):
        self.mode = mode
        self.book = num_ranks // 2
        self.num_ranks = num_ranks

    def Deal(self):
       return Deal(self.mode)

    def random_deal(self, rng):
        deal = self.Deal()
        dealer = _seats.tokens[rng.randrange(4)]
        deal = self.set_dealer(deal, dealer)
        vulnerability_mask = rng.randrange(4)
        deal.vulnerability = []
        if vulnerability_mask & 1:
            deal.vulnerability.extend(["North", "South"])
        if vulnerability_mask & 2:
            deal.vulnerability.extend(["East", "West"])
        deal = self.set_players(deal, 
                "Rodwell",
                "Platnick",
                "Meckstroth",
                "Diamond")

        played_cards = [(suit, rank) for suit in range(4)
            for rank in range(13 - self.num_ranks)]
        unplayed_cards = [(suit, rank) for suit in range(4)
            for rank in range(13 - self.num_ranks, 13)]
        rng.shuffle(unplayed_cards)
        for i, card in enumerate(played_cards + unplayed_cards):
            deal._state.give_card(i % 4, card[0], card[1])

        deal._state.max_length[:] = deal._state.min_length
        deal._state.played_cards[:,:13 - self.num_ranks] = 1
        return deal

    def distinct_boards(self):
        return [self.set_board_number(self.Deal(), n) for n in range(1, 17)]

    def accept_claim(self, deal, total_tricks):
        if not deal.contract_level():
            self._set_error(deal, "claim before bidding finished")
            return deal
        deal._state.stage = DealState.STAGE_SCORING

        tricks_contracted = int(deal.contract_level()) + self.book
        diff = int(total_tricks) - tricks_contracted
        if diff == 0:
            outcome = "="
        elif diff < 0:
            outcome = str(diff)
        else:
            outcome = "+" + str(diff)
        result = Event([
            deal.contract_level(),
            deal.contract_strain(),
            deal.contract_seat(),
            deal.contract_doubled(),
            outcome])

        if deal.result:
            if deal.result.tokens != result.tokens:
                self._set_error(deal, "claim/result mismatch")
        else:
            deal.result = result
        return deal

    def compute_score(self, deal):
        assert deal.is_final()
        counts = deal.trick_counts()
        declarer = deal.contract_seat()
        if declarer:
            declarer_ix = _seats.index[declarer]
            total_tricks = 0
            for seat, n in counts.items():
                if _seats.index[seat] % 2 == declarer_ix % 2:
                    total_tricks += n
            self.accept_claim(deal, total_tricks)
        else:
            tokens = ["passed_out"]*5
            self.set_result(deal, *tokens)

    def table_score(self, result_event, vulnerability_list):
        """table_score computes the score at a table.

        Bridge score explained by `https://www.acbl.org/learn_page/how-to-play-bridge/how-to-keep-score/duplicate/`

        Args:
          result_event: the result of play, from deal.result.
          vulnerability_list: either [], ["North", "South"], ...

        Returns:
          (score for North-South, score for East-West).
        """
        (level, strain, seat, double, outcome) = result_event.tokens
        if level == "passed_out":
            return (0, 0)
        vulnerable = seat in vulnerability_list
        declarer_score, defender_score = (None, None)
        if outcome == "=":
            trick_diff = 0
        else:
            trick_diff = int(outcome)

        if trick_diff < 0:
            if double == "undoubled":
                if vulnerable:
                    defender_score = 100 * abs(trick_diff)
                else:
                    defender_score = 50 * abs(trick_diff)
            else:
                if vulnerable:
                    if trick_diff >= -3:
                        defender_score = (200, 500, 800)[abs(trick_diff) - 1]
                    else:
                        defender_score = 800 + 300 * (abs(trick_diff) - 3)
                else:
                    if trick_diff >= -3:
                        defender_score = (100, 300, 500)[abs(trick_diff) - 1]
                    else:
                        defender_score = 500 + 300 * (abs(trick_diff) - 3)
                if double == "redoubled":
                    defender_score *= 2
        else:
            if strain == "notrump":
                below_line_score = 40 + 30 * (int(level) - 1)
                above_line_score = 30 * trick_diff
            elif strain in ["Spades", "Hearts"]:
                below_line_score = 30 * (int(level))
                above_line_score = 30 * trick_diff
            elif strain in ["Diamonds", "Clubs"]:
                below_line_score = 20 * (int(level))
                above_line_score = 20 * trick_diff

            if double != "undoubled":
                below_line_score *= 2
                if vulnerable:
                    above_line_score = 50 + 200 * trick_diff
                else:
                    above_line_score = 50 + 100 * trick_diff
                if double == "redoubled":
                    below_line_score *= 2
                    above_line_score *= 2

            if below_line_score >= 100:
                if vulnerable:
                    bonus = 500
                else:
                    bonus = 300
            else:
                bonus = 50

            if level == "6":
                if vulnerable:
                    bonus += 750
                else:
                    bonus += 500
            elif level == "7":
                if vulnerable:
                    bonus += 1500
                else:
                    bonus += 1000

            declarer_score = below_line_score + above_line_score + bonus

        if seat in ["North", "South"]:
            return declarer_score, defender_score
        else:
            return defender_score, declarer_score

    def comparison_score(self, diff, scoring):
        if scoring == "Matchpoints":
            if diff > 0:
                return 1, None
            elif diff < 0:
                return -1, None
            else:
                return 0, None
        elif scoring == "total_points":
            return diff, None
        elif scoring == "IMPs":
            for i, cutoff in enumerate(_IMP_table):
                if abs(diff) < cutoff:
                    if diff > 0:
                        return i, None
                    else:
                        return -i, None
            return None, "score diff impossibly large"
        else:
            return None, "unknown scoring"

    def set_dealer_index(self, deal, dealer_ix):
        if deal._state.next_to_act is None:
            deal._state.next_to_act = dealer_ix
            deal._state.stage = DealState.STAGE_BIDDING
        else:
            self._set_error(deal, "dealer already set")
        return deal

    def set_dealer(self, deal, dealer):
        seat_ix = _seats.index[dealer]
        return self.set_dealer_index(deal, seat_ix)

    def set_board_number(self, deal, n):
        deal = self.set_dealer(deal,
            ["North", "East", "South", "West"][(n - 1) % 4])
        deal.vulnerability = [
            [],
            ["North", "South"],
            ["East", "West"],
            ["North", "South", "East", "West"]
        ][((n - 1) + (n - 1) // 4) % 4]
        return deal

    def set_players(self, deal, south, west, north, east):
        deal.players = {
                "South": south.lower(),
                "West": west.lower(),
                "North": north.lower(),
                "East": east.lower()}
        return deal

    def set_result(self, deal, level, strain, player, double, outcome):
        """ Sets deal.result."""
        if (level not in _levels.index or
            strain not in _strains.index or
            player not in _seats.index or
            double not in _extra.index or
            outcome not in _outcomes.index):
            level, strain, player, double, outcome = ["passed_out"]*5

        deal.result = Event([level, strain, player, double, outcome])
        return deal

    def give_card(self, deal, seat, suit, rank):
        seat_ix = _seats.index[seat]
        suit_ix = _suits.index[suit]
        rank_ix = _ranks.index[rank]
        deal._state.give_card(seat_ix, suit_ix, rank_ix)
        return deal

    def give_cards(self, deal, cards_list):
        """Batch version of give_cards."""
        cards = np.copy(deal._state.dealt_cards)
        for seat, suit, rank in cards_list:
            seat_ix = _seats.index[seat]
            suit_ix = _suits.index[suit]
            rank_ix = _ranks.index[rank]
            if cards[seat_ix, suit_ix, rank_ix]:
                self._set_error(deal, "Duplicate card")
                break
            cards[seat_ix, suit_ix, rank_ix] = 1
        deal._state.add_cards(None, cards)
        return deal
    
    def possible_actions(self, deal):
        possible_ids = self.possible_action_indices(deal)
        actor = deal._state.next_to_act
        return [_make_action_event(actor, i) for i in possible_ids]

    def possible_action_indices(self, deal):
        possible = []
        state = deal._state
        actor_ix = state.next_to_act
        if state.stage == DealState.STAGE_BIDDING:
            if not state.bidding_is_open:
                return list(range(36))
            last_bid_action_id = \
                    5 * state.last_bid_level + state.last_bid_strain
            possible = list(range(last_bid_action_id + 1, 35))
            for i, call in enumerate(_calls.tokens):
                hdeal = self.make_call(deal.copy_replay_state(), call)
                if not hdeal.error:
                    possible.append(35 + i)
        else:
            if state.dealt_cards[actor_ix, :, :].sum() == 13:
                cards_left = (state.dealt_cards[actor_ix, :, :] & ~state.played_cards[:, :])
                follow_suit = state.trick_suit
                if state.trick_position == 0:
                    follow_suit = None
                if follow_suit is not None and \
                        cards_left[follow_suit].sum() == 0:
                    follow_suit = None
                for suit in range(4):
                    if follow_suit is not None and suit != follow_suit:
                        continue
                    for rank in range(13):
                        if cards_left[suit][rank]:
                            possible.append(38 + 13 * suit + rank)
            else:
                for i, suit in enumerate(_suits.tokens):
                    for j, rank in enumerate(_ranks.tokens):
                        hdeal = self.play_card(copy.deepcopy(deal), suit, rank)
                        if not hdeal.error:
                            possible.append(38 + 13 * i + j)
        return possible

    def make_bid(self, deal, level, strain):
        level_ix = _levels.index[level]
        strain_ix = _strains.index[strain]
        return self.execute_action_ids(deal, [5 * level_ix + strain_ix])

    def make_call(self, deal, call):
        call_ix = _calls.index[call]
        return self.execute_action_ids(deal, [35 + call_ix])

    def play_card(self, deal, suit, rank):
        suit_ix = _suits.index[suit]
        rank_ix = _ranks.index[rank]
        return self.execute_action_ids(deal, [38 + 13 * suit_ix + rank_ix])

    def execute_action(self, deal, action):
        if action.is_bid():
            return self.make_bid(deal, action.level(), action.strain())
        elif action.is_call():
            return self.make_call(deal, action.tokens[2])
        elif action.is_play():
            return self.play_card(deal, action.suit(), action.rank())

    def execute_action_index(self, deal, action_id):
        return self.execute_action_ids(deal, [action_id])

    def execute_action_ids(self, deal, action_ids):
        l = deal._history_length
        n = deal._state.execute_action_ids(action_ids, deal._history[l:,:])
        deal._history_length += n
        return deal

    def _set_error(self, deal, msg):
        deal._state.set_error(msg)
        return deal

    def kibitzer_view(self, deal, action_index):
        view = self._replay(deal, action_index)
        view._state.add_cards(None, deal._state.dealt_cards)
        return view

    def table_view(self, deal, action_index):
        view = self._replay(deal, action_index)
        return view

    def actor_view(self, deal, action_index):
        view = self._replay(deal, action_index)
        actor_ix = view._state.next_to_act
        if actor_ix is None:
            view._state.add_cards(None, deal._state.dealt_cards)
            return view
        if view._state.stage == DealState.STAGE_PLAY:
            if actor_ix % 2 == view._state.declarer % 2:
                view._state.add_cards(view._state.declarer, deal._state.dealt_cards)
            else:
                view._state.add_cards(actor_ix, deal._state.dealt_cards)
        else:
            view._state.add_cards(actor_ix, deal._state.dealt_cards)
        return view

    def _replay(self, deal, action_index):
        """Creates a public-information view, replaying each call and play."""
        view = self.Deal()
        view.board_name = deal.board_name
        view.table_name = deal.table_name
        view.players = deal.players
        view.vulnerability = deal.vulnerability
        view.scoring = deal.scoring
        view.result = deal.result
        view = self.set_dealer(view, deal.dealer())
        view = self.execute_action_ids(view, deal._history[:action_index,1])
        if view._state.stage == DealState.STAGE_SCORING:
            view._state.add_cards(None, deal._state.dealt_cards)
        elif view._state.dummy_is_public():
            dummy_ix = (view._state.declarer + 2) % 4
            view._state.add_cards(dummy_ix, deal._state.dealt_cards)
        return view

    def add_explanation(self, deal, explanation):
        return deal  #TODO

    def add_commentary(self, deal, comment):
        return deal  #TODO


class Deal:
    def __init__(self, mode):
        if mode == MODE_DEBUG:
            self._state = DebugDealState()
        else:
            self._state = FastDealState()
        self._history = np.full((35 * 9 + 52, 2), -1, dtype=np.int8)
        self._history_length = 0

        self.board_name = None
        self.table_name =  None
        self.players =  None
        self.vulnerability =  None
        self.scoring =  None
        self.result = None

    @property
    def error(self):
        if self._state.stage == DealState.STAGE_ERROR:
            return self._state.error_message

    def copy_replay_state(self):
        new_deal = copy.copy(self)
        new_deal._state = copy.copy(self._state)
        new_deal._state._vector = self._state._vector.copy()
        new_deal._history = self._history.copy()
        return new_deal

    def history_string(self):
        return '+'.join(self._history[:self.history_length, 1])

    def _dealer_ix(self):
        if self._history_length > 0:
            return self._history[0,0]
        else:
            return self._state.next_to_act

    def dealer(self):
        return _seats.tokens[self._dealer_ix()]

    def num_actions(self):
        return self._history_length
    
    def action(self, n):
        return _make_action_event(self._history[n,0],self._history[n,1])

    def trick_counts(self):
        return {s: n for s,n in zip(_seats.tokens, self._state.tricks_taken)}

    def next_to_act(self):
        n = self._state.next_to_act
        if n is None:
            return None
        return _seats.tokens[n]

    def next_to_act_index(self):
        return self._state.next_to_act

    def next_action_verb_index(self):
        bid_or_play = "bids" if self.contract_index == -1 else "plays"
        token = "{}_{}".format(self.next_to_act(), bid_or_play)
        return _action_verbs.index[token]

    def contract_strain(self):
        if self._state.stage in (DealState.STAGE_PLAY, DealState.STAGE_SCORING):
            if self._state.last_bid_strain is not None:
                return _strains.tokens[self._state.last_bid_strain]

    def contract_level(self):
        if self._state.stage in (DealState.STAGE_PLAY, DealState.STAGE_SCORING):
            if self._state.last_bid_level is not None:
                return _levels.tokens[self._state.last_bid_level]

    def contract_seat(self):
        if self._state.declarer is not None:
            return _seats.tokens[self._state.declarer]

    def contract_doubled(self):
        if self._state.declarer is not None:
            prefix = ['un','', 're'][self._state.last_bid_double]
            return prefix + "doubled"

    def is_final(self):
        return self._state.stage == DealState.STAGE_SCORING

    def last_bid_level(self):
        if self._state.last_bid_level is not None:
            return _levels.tokens[self._state.last_bid_level]

    def last_bid_strain(self):
        if self._state.last_bid_strain is not None:
            return _strains.tokens[self._state.last_bid_strain]

    def last_bid_seat(self):
        if self._state.last_bid_seat is not None:
            return _seats.tokens[self._state.last_bid_seat]

    def last_double_as_call(self):
        if self._state.last_bid_double is not None:
            return _calls.tokens[self._state.last_bid_double]
        return _calls.tokens[0]

    def contract_doubled_as_call(self):
        if (self._state.stage != DealState.STAGE_BIDDING and
                self._state.last_bid_double is not None):
            return _calls.tokens[self._state.last_bid_double]

    def pass_position(self):
        return self._state.pass_position

    def first_seat_of_partnership_to_mention_suit(self):
        return self._state.first_to_mention

    def trick_suit(self):
        if self._state.trick_suit is not None:
            return _suits.tokens[self._state.trick_suit]

    def trick_winning_seat(self):
        if self._state.trick_winning_seat is not None:
            return _seats.tokens[self._state.trick_winning_seat]

    def trick_winning_suit(self):
        if self._state.trick_winning_suit is not None:
            return _suits.tokens[self._state.trick_winning_suit]

    def trick_winning_rank(self):
        if self._state.trick_winning_rank is not None:
            return _ranks.tokens[self._state.trick_winning_rank]

    @property
    def dealt_cards(self):
        return self._state.dealt_cards

    @property
    def played_cards(self):
        return self._state.played_cards


class OldGame:
    def random_deal(self, rng):
        deal = Deal()
        dealer = _seats.tokens[rng.randrange(4)]
        deal = self.set_dealer(deal, dealer)
        vulnerability_mask = rng.randrange(4)
        vulnerability = []
        deal.set_scoring("IMPs")
        if vulnerability_mask & 1:
            vulnerability.extend(["North", "South"])
        if vulnerability_mask & 2:
            vulnerability.extend(["East", "West"])
        deal.set_vulnerability(vulnerability)
        deal = self.set_players(deal, {
                "South": "Rodwell",
                "West": "Platnick",
                "North": "Meckstroth",
                "East": "Diamond"})
        cards = [(suit, rank) for suit in range(4) for rank in range(13)]
        rng.shuffle(cards)
        for i, card in enumerate(cards):
            self._give_card(deal, i % 4, card[0], card[1])
        return deal

    def deal_from_played_game(self, played_game):
        deal = self.Deal()
        deal.players = {k: v.player_name
                for k, v in played_game.player.items()}
        for seat, hand in played_game.board.dealt_cards.items():
            for t in hand.card_token:
                suit, rank = t.split("_")
                self.give_card(deal, seat, suit, rank)
        deal.vulnerability = played_game.board.vulnerable_seat
        deal.board_name = played_game.board.board_sequence_name
        deal.scoring = played_game.board.scoring

        deal = self.set_dealer(deal, played_game.board.dealer)
        annotation_index = 0

        def add_commentary(deal, ann):
            if ann.explanation:
                return self.add_explanation(deal, ann.explanation)
            if ann.kibitzer_comment:
                return self.add_commentary(deal, ann.kibitzer_comment)

        for i, action in enumerate(played_game.actions):
            while (annotation_index < len(played_game.annotations) and
                played_game.annotations[annotation_index].action_index <= i):
                deal = add_commentary(deal, played_game.annotations[annotation_index])
                annotation_index += 1

            if action.token in _calls.tokens:
                deal = self.make_call(deal, action.token)
            elif action.token in _bids.tokens:
                deal = self.make_bid(deal, *action.token.split("_"))
            elif action.token in _cards.tokens:
                deal = self.play_card(deal, *action.token.split("_"))

        while annotation_index < len(played_game.annotations):
            deal = add_commentary(deal, played_game.annotations[annotation_index])
            annotation_ndex += 1

        deal.table_name = played_game.table_name
        if len(played_game.result.summary_token) == 5:
            deal = self.set_result(deal, *played_game.result.summary_token)
        return deal

    def played_game_from_deal(self, deal):
        """Doesn't set result.comparison_score."""
        player_ids = {k: alphabridge_pb2.PlayerId(player_name=v)
                for k, v in deal.players.items()}
        dealt_cards = {"South": [], "West": [], "North": [], "East": []}
        for i, seat in enumerate(_seats.tokens):
            for j, suit in enumerate(_suits.tokens):
                for k, rank in enumerate(_ranks.tokens):
                    if deal.dealt_cards[i, j, k]:
                        dealt_cards[seat].append("{}_{}".format(suit, rank))
        board = alphabridge_pb2.Board(
                vulnerable_seat=deal.vulnerability,
                board_sequence_name=deal.board_name,
                scoring=deal.scoring,
                dealer=deal.dealer(),
                dealt_cards={k: alphabridge_pb2.Hand(card_token=v)
                    for k, v in dealt_cards.items()})
        actions = []
        annotations = []
        for event in deal.events:
            if event.is_bid() or event.is_play():
                actions.append(alphabridge_pb2.Action(
                        token="{}_{}".format(event.tokens[2], event.tokens[3])))
            elif event.is_call():
                actions.append(alphabridge_pb2.Action(
                        token=event.tokens[2]))
            if event.explanation:
                annotations.append(alphabridge_pb2.Annotation(
                    action_index=len(actions), explanation=event.explanation))
            for comment in event.commentary:
                annotations.append(alphabridge_pb2.Annotation(
                    action_index=len(actions), kibitzer_comment=comment))

        if deal.result:
            result = alphabridge_pb2.Result(summary_token=deal.result.tokens)
        else:
            result = alphabridge_pb2.Result()
        played_game = alphabridge_pb2.PlayedGame(
                player=player_ids,
                board=board,
                actions=actions,
                annotations=annotations,
                result=result,
                table_name=deal.table_name)
        return played_game

    def set_dealer(self, deal, seat):
        if deal.events:
            deal.error = "dealer already set"
        else:
            seat_ix = _seats.index[seat]
            deal.events = [_make_deal_event(seat_ix)]
        return deal

    def _finalize(self, deal):
        deal._is_final = True
        counts = deal.trick_counts()
        declarer = deal.contract_seat()
        declarer_ix = _seats.index[declarer]
        total_tricks = 0
        for seat, n in counts.items():
            if _seats.index[seat] % 2 == declarer_ix % 2:
                total_tricks += n
        self._accept_claim(deal, total_tricks)


    def add_explanation(self, deal, explanation):
        if len(deal.events) == 0:
            deal.error = "explanation with no events"
            return deal
        if deal.events[-1].explanation is not None:
            deal.error = "explanation already set"
            return deal
        deal.events[-1].explanation = explanation
        return deal

    def add_commentary(self, deal, comment):
        if len(deal.events) == 0:
            deal.error = "comment with no events"
            return
        deal.events[-1].commentary.append(comment)
        return deal

    def execute_action_index(self, deal, index):
        token = _actions.rindex[index]
        if token in _cards.index:
            return self.play_card(deal, *token.split("_"))
        elif token in _bids.index:
            return self.make_bid(deal, *token.split("_"))
        else:
            return self.make_call(deal, token)


    def score_played_board(self, played_board):
        for game in played_board.tables:
            if game.result.summary_token:
                scores = self.table_score(Event(game.result.summary_token),
                        game.board.vulnerable_seat)
                game.result.table_score = scores[0] if scores[0] else -scores[1]
            else:
                game.result.table_score = 1 # No score

        for game in played_board.tables:
            comparison_score = 0
            for other_game in played_board.tables:
                if other_game != game and \
                        game.result.table_score != 1 and \
                        other_game.result.table_score != 1:
                    score, err = self.comparison_score(
                            game.result.table_score - other_game.result.table_score,
                            game.board.scoring)
                    comparison_score += score
            game.result.comparison_score = comparison_score

    def same_side(self, a, b):
        d = {"North": 0, "South": 0, "East": 1, "West": 1}
        return d[a] == d[b]

    def same_side_for_index(self, ia, ib):
        return (ia - ib) % 2 == 0

    def all_same_side_for_index(self, ia, ib, ic):
        return (all(x is not None for x in [ia, ib, ic]) and
                (ia - ib) % 2 == 0 and (ia - ic) % 2 == 0)


def dealcards(m):
    return " ".join(f"{p}: {suitcards(m[k])}" for k, p in enumerate("SWNE"))


def suitcards(mat):
    s = ""
    for i, n in enumerate("CDHS"):
        s += n
        for j, m in enumerate("23456789TJQKA"):
            if mat[i][j]:
                s += m
        s += " "
    return s


class OldDeal:
    """Represents a position in the bidding and play of the cards."""
    def __init__(self):
        self.board_name = None
        self.table_name =  None
        self.players =  None
        self.vulnerability =  None
        self.scoring =  None

        self.dealt_cards =  np.zeros((4,4,13), np.int8)  # seat, suit, rank. 1=has.
        self.played_cards = np.zeros((4, 13), np.int8)  # suit, rank. 1=played.
        self.events = []
        self.no_cards = np.full((4,4), -1, np.int16)  # seat, suit. n=event index, -1=None.
        self.first_mention = np.zeros((4,5), np.int8)  # seat, strain. 1=first
        self.contract_index = -1
        self._is_final = False

        self.result = None
        self.error = None

    def __repr__(self):
        buf = ""
        buf += "board {}{}\n".format(self.table_name, self.board_name)
        buf += "players {}\n".format(self.players)
        buf += "vulnerability {}\n".format(self.vulnerability)
        buf += "scoring {}\n".format(self.scoring)
        buf += "dealt_cards: {}\n".format(dealcards(self.dealt_cards))
        buf += "played_cards: {}\n".format(suitcards(self.played_cards))
        buf += "no_cards:\n{}\n".format(self.no_cards)
        buf += "first_mention:\n{}\n".format(self.first_mention)
        buf += "events:\n"
        for event in self.events:
            buf += "  {}\n".format(event)
        return buf

    def __str__(self):
        return self.__repr__()

    def has_error(self):
        return self.error is not None

    def next_to_act(self):
        if not self.events:
            return None
        else:
            event = self.events[-1]
            if event.is_call() or event.is_play() or event.is_contract():
                seat_ix = _seats.index[event.seat()]
                next_seat_ix = (seat_ix + 1) % 4
                return _seats.rindex[next_seat_ix]
            else:
                return self.events[-1].seat()

    def last_bid(self):
        for event in reversed(self.events):
            if event.is_bid():
                return event
        return None

    def last_bid_level(self):
        b = self.last_bid()
        if b:
            return b.level()
        else:
            return None

    def last_bid_strain(self):
        b = self.last_bid()
        if b:
            return b.strain()
        else:
            return None

    def last_bid_seat(self):
        b = self.last_bid()
        if b:
            return b.seat()
        else:
            return None

    def last_double(self):
        for event in reversed(self.events):
            if event.is_double() or event.is_redouble():
                return event
            elif not event.is_pass():
                return None

    def trailing_pass_count(self):
        count = 0
        for event in reversed(self.events):
            if event.is_pass():
                count += 1
            else:
                break
        return count

    def pass_position(self):
        return self.trailing_pass_count()

    def last_lead(self):
        lead_event = None
        for event in reversed(self.events):
            if event.is_play():
                lead_event = event
            elif event.is_trick() or event.is_contract():
                break
        return lead_event

    def num_actions(self):
        count = 0
        for event in self.events:
            if event.is_bid() or event.is_call() or event.is_play():
                count += 1
        return count

    def action(self, action_num):
        count = 0
        for event in self.events:
            if event.is_bid() or event.is_call() or event.is_play():
                if count == action_num:
                    return event
                count += 1

    def contract_seat_index(self):
        if self.contract_index == -1:
            return None
        else:
            return _seats.index[self.events[self.contract_index].seat()]

    def contract_doubled(self):
        if self.contract_index == -1:
            return None
        else:
            return self.events[self.contract_index].doubled()

    def contract_doubled_as_call(self):
        translation = {
                None: None,
                'undoubled': 'pass',
                'doubled': 'double',
                'redoubled': 'redouble',
        }
        return translation[self.contract_doubled()]

    def is_final(self):
        return self._is_final

    def are_ns_vulnerable(self):
        return "North" in self.vulnerability

    def are_ew_vulnerable(self):
        return "East" in self.vulnerability

    def first_seat_of_partnership_to_mention_suit(self):
        return self.first_mention

    def trick_suit(self):
        event = self.last_lead()
        if event:
            return event.suit()

    def trick_winning_seat(self):
        ev = self.trick_winner()
        if ev:
            return ev.seat()

    def trick_winning_suit(self):
        ev = self.trick_winner()
        if ev:
            return ev.suit()

    def trick_winning_rank(self):
        ev = self.trick_winner()
        if ev:
            return ev.rank()


class Event(object):
    """Wrapper around an array of tokens."""
    def __init__(self, tokens, commentary=None, explanation=None):
        self.tokens = tokens
        self.commentary = commentary or []
        self.explanation = explanation

    def __str__(self):
        return str(self.tokens)

    def is_bid(self):
        return (len(self.tokens) == 4 and
                self.tokens[0] in _seats.index and
                self.tokens[1] == "bids" and
                self.tokens[2] in _levels.index and
                self.tokens[3] in _strains.index)

    def is_pass(self):
        return (len(self.tokens) == 4 and
                self.tokens[0] in _seats.index and
                self.tokens[1] == "bids" and
                self.tokens[2] == "pass")

    def is_double(self):
        return (len(self.tokens) == 4 and
                self.tokens[0] in _seats.index and
                self.tokens[1] == "bids" and
                self.tokens[2] == "double")

    def is_redouble(self):
        return (len(self.tokens) == 4 and
                self.tokens[0] in _seats.index and
                self.tokens[1] == "bids" and
                self.tokens[2] == "redouble")

    def is_call(self):
        return self.is_bid() or self.is_pass() or self.is_double() or self.is_redouble()

    def is_play(self):
        return (len(self.tokens) == 4 and
                self.tokens[0] in _seats.index and
                self.tokens[1] == "plays" and
                self.tokens[2] in _suits.index and
                self.tokens[3] in _ranks.index)

    def is_contract(self):
        return (len(self.tokens) == 5 and
                self.tokens[0] in _seats.index and
                self.tokens[1] == "declares" and
                self.tokens[2] in _levels.index and
                self.tokens[3] in _strains.index)

    def is_result(self):
        return (len(self.tokens) == 5 and
                self.tokens[0] in _levels.index and
                self.tokens[1] in _strains.index and
                self.tokens[2] in _seats.index and
                self.tokens[4] in _outcomes.index)

    def is_trick(self):
        return (len(self.tokens) == 2 and
                self.tokens[0] in _seats.index and
                self.tokens[1] == "takes_trick")

    def seat(self):
        if len(self.tokens) > 0 and self.tokens[0] in _seats.index:
            return self.tokens[0]

    def strain(self):
        if len(self.tokens) > 3 and self.tokens[3] in _strains.index:
            return self.tokens[3]

    def level(self):
        if len(self.tokens) > 2 and self.tokens[2] in _levels.index:
            return self.tokens[2]

    def doubled(self):
        if len(self.tokens) > 4:
            return self.tokens[4]

    def suit(self):
        if self.is_play():
            return self.tokens[2]

    def rank(self):
        if self.is_play():
            return self.tokens[3]

    def outcome(self):
        if self.is_result():
            return self.tokens[4]
            


class Tokens(object):
    def __init__(self, tokens):
        self.tokens = tokens
        self.index = {v:i for i, v in enumerate(tokens)}
        self.rindex = {i:v for i, v in enumerate(tokens)}


_extra = Tokens([
    "[PAD]", "[MASK]", "[ACTION]", "[RESULT]", "[SCORE]", "[TO_ACT]",
    "[CONTRACT_SEAT]", "deals", "undoubled", "doubled", "redoubled",
    "passed_out", "declares", "takes_trick", "gets", "sits", "vulnerable"])


_scorings = Tokens(["Matchpoints", "IMPs", "total_points"])


_seats = Tokens(["South", "West", "North", "East"])


_suits = Tokens(["Club", "Diamond", "Heart", "Spade"])


_ranks = Tokens(["Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
    "Nine", "Ten", "Jack", "Queen", "King", "Ace"])


_strains = Tokens(["Clubs", "Diamonds", "Hearts", "Spades", "notrump"])


_levels = Tokens(["1", "2", "3", "4", "5", "6", "7"])

# NOTE: all outcomes are included in _scores.
#       consequently, we don't include them in all_tokens.
_outcomes = Tokens([str(x) for x in range(-13,0)] + ["="] +
                   [ "+" + str(x) for x in range(1,6)])

_scores = Tokens([str(x) for x in range(-24,0)] + ["="] +
                   [ "+" + str(x) for x in range(1,25)])

_cards = Tokens(["{}_{}".format(s, r)
                 for s in _suits.tokens for r in _ranks.tokens])

_bids = Tokens(["{}_{}".format(l, s)
                for l in _levels.tokens for s in _strains.tokens])

_calls = Tokens(["pass", "double", "redouble"])

_action_verbs = Tokens(["{}_bids".format(s) for s in _seats.tokens] +
                       ["{}_plays".format(s) for s in _seats.tokens])

_actions = Tokens(_bids.tokens + _calls.tokens + _cards.tokens)

# TODO: move these into _extra
_new_tokens = Tokens(["[HIDDEN]"])

all_tokens = Tokens(
    _extra.tokens +
    _actions.tokens + _scores.tokens + _action_verbs.tokens +
    _scorings.tokens + _seats.tokens +
    [t[1].lower() for t in players.players_by_frequency] +
    _new_tokens.tokens)

num_actions = len(_actions.tokens)
num_scores = len(_scores.tokens)
num_action_verbs = len(_action_verbs.tokens)
first_action_id = all_tokens.index[_actions.tokens[0]]
first_score_id = all_tokens.index[_scores.tokens[0]]
first_action_verb_id = all_tokens.index[_action_verbs.tokens[0]]


_IMP_table = [ 20, 50, 90, 130, 170, 220, 270, 320, 370, 430, 500, 600, 750,
        900, 1100, 1300, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 5000, 1e99 ]


def _make_deal_event(seat_ix):
    seat = _seats.rindex[seat_ix]
    return Event([seat, "deals"])


def _make_call_event(seat_ix, call):
    seat = _seats.rindex[seat_ix]
    return Event([seat, "bids", call, "[PAD]"])


def _make_bid_event(seat_ix, level_ix, strain_ix):
    seat = _seats.rindex[seat_ix]
    level = _levels.rindex[level_ix]
    strain = _strains.rindex[strain_ix]
    return Event([seat, "bids", level, strain])


def _make_passed_out_event():
    return Event(["passed_out"])

def _make_contract_event(seat, bid_event, double_event):
    if double_event:
        if double_event.is_double():
            double_token = "doubled"
        else:
            double_token = "redoubled"
    else:
        double_token = "undoubled"
    return Event([seat, "declares", bid_event.level(), bid_event.strain(), double_token])

def _make_play_event(seat_ix, suit_ix, rank_ix):
    seat = _seats.rindex[seat_ix]
    suit = _suits.rindex[suit_ix]
    rank = _ranks.rindex[rank_ix]
    return Event([seat, "plays", suit, rank])

def _make_action_event(seat_ix, action_ix):
    if action_ix < 35:
        return _make_bid_event(seat_ix, action_ix // 5, action_ix % 5)
    elif action_ix < 38:
        return _make_call_event(seat_ix, _calls.tokens[action_ix - 35])
    else:
        card_ix = action_ix - 38
        return _make_play_event(seat_ix, card_ix // 13, card_ix % 13)

def _make_trick_event(seat):
    return Event([seat, "takes_trick"])

if __name__ == "__main__":
    print(len(all_tokens.tokens))
