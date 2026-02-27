"""Hi-Lo — Card probability (higher/lower) with streak multiplier."""
from sim_engine.rmg.base import BaseRMGEngine


class HiLoEngine(BaseRMGEngine):
    game_type = "hilo"
    display_name = "Hi-Lo"
    house_edge_range = (0.02, 0.04)

    def generate_config(self, house_edge: float = 0.03, deck_size: int = 52,
                        max_streak: int = 10, **kw) -> dict:
        return {
            "game_type": "hilo",
            "house_edge": max(0.01, min(0.08, house_edge)),
            "deck_size": deck_size,
            "card_values": 13,  # A through K
            "max_streak": max_streak,
        }

    def compute_house_edge(self, config: dict) -> float:
        """Compute effective house edge including tie probability.
        Ties (same card) always lose, adding implicit edge on top of the stated edge."""
        he = config.get("house_edge", 0.03)
        card_vals = config.get("card_values", 13)
        # Probability of a tie = 1/card_vals (for each card value)
        # Average tie probability across all starting cards
        tie_prob = 1.0 / card_vals
        # Effective house edge = stated_he + (1-stated_he) * tie_impact
        # But more accurately: compute expected return
        total_ev = 0.0
        for current in range(1, card_vals + 1):
            # Optimal strategy: guess higher if current <= mid, else lower
            if current <= card_vals // 2:
                win_count = card_vals - current  # cards strictly higher
            else:
                win_count = current - 1  # cards strictly lower
            win_prob = win_count / card_vals  # out of all next cards (including tie)
            if win_prob > 0:
                fair_win_prob = win_count / (card_vals - 1)  # prob excluding tie
                multiplier = (1.0 - he) / fair_win_prob if fair_win_prob > 0 else 0
                total_ev += (1.0 / card_vals) * win_prob * multiplier
        return max(0, 1.0 - total_ev)

    def simulate_round(self, config: dict, rng) -> float:
        he = config.get("house_edge", 0.03)
        card_vals = config.get("card_values", 13)

        # For RTP measurement: single round (no streak compounding)
        current_card = rng.randint(1, card_vals)
        next_card = rng.randint(1, card_vals)

        # Tie = loss (house edge mechanism)
        if next_card == current_card:
            return 0.0

        # Player uses optimal strategy
        if current_card <= card_vals // 2:
            correct = next_card > current_card
        else:
            correct = next_card < current_card

        if not correct:
            return 0.0

        # Fair multiplier for optimal guess
        if current_card <= card_vals // 2:
            win_prob = (card_vals - current_card) / (card_vals - 1)
        else:
            win_prob = (current_card - 1) / (card_vals - 1)

        if win_prob <= 0:
            return 0.0
        return (1.0 - he) / win_prob
