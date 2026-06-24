from __future__ import annotations

from dataclasses import asdict, dataclass

SCHEMA_VERSION = "mlb-feature-store-contract.v1"


@dataclass(frozen=True, slots=True)
class FeatureField:
    name: str
    group: str
    dtype: str
    description: str
    pregame_safe: bool = True
    nullable: bool = True


FEATURE_FIELDS: tuple[FeatureField, ...] = (
    FeatureField("date", "identity", "date", "Slate date.", nullable=False),
    FeatureField("season", "identity", "int", "MLB season.", nullable=False),
    FeatureField("game_pk", "identity", "string", "MLB StatsAPI game identifier."),
    FeatureField("player_id", "identity", "string", "Player identifier when available."),
    FeatureField("player", "identity", "string", "Player display name.", nullable=False),
    FeatureField("team", "identity", "string", "Player team abbreviation.", nullable=False),
    FeatureField("opponent", "identity", "string", "Opponent team abbreviation."),
    FeatureField("market", "market", "string", "Normalized player prop market.", nullable=False),
    FeatureField("side", "market", "string", "Over/under side."),
    FeatureField("line", "market", "float", "Offered prop line."),
    FeatureField("book", "market", "string", "Sportsbook/source book name."),
    FeatureField("american_odds", "market", "int", "American odds at collection time."),
    FeatureField("implied_probability_percent", "market", "float", "Market implied probability."),
    FeatureField("book_count", "market", "int", "Count of books represented by the row."),
    FeatureField("consensus_open_total", "gameContext", "float", "Pregame consensus game total at open."),
    FeatureField("consensus_current_total", "gameContext", "float", "Latest pregame consensus game total."),
    FeatureField("team_no_vig_win_prob_current", "gameContext", "float", "No-vig team win probability before first pitch."),
    FeatureField("moneyline_movement", "gameContext", "float", "Pregame moneyline movement."),
    FeatureField("park_factor_runs", "gameContext", "float", "Run environment park factor."),
    FeatureField("probable_pitcher_hand", "gameContext", "string", "Probable opposing pitcher handedness."),
    FeatureField("weather_temperature_f", "weather", "float", "Open-Meteo forecast temperature."),
    FeatureField("weather_wind_mph", "weather", "float", "Open-Meteo forecast wind speed."),
    FeatureField("weather_wind_direction", "weather", "string", "Open-Meteo forecast wind direction."),
    FeatureField("weather_humidity", "weather", "float", "Open-Meteo forecast humidity."),
    FeatureField("batter_xba", "batterSavant", "float", "Batter expected batting average."),
    FeatureField("batter_xslg", "batterSavant", "float", "Batter expected slugging."),
    FeatureField("batter_barrel_rate", "batterSavant", "float", "Batter barrel rate."),
    FeatureField("batter_hard_hit_rate", "batterSavant", "float", "Batter hard-hit rate."),
    FeatureField("pitcher_xwoba_allowed", "pitcherSavant", "float", "Pitcher expected wOBA allowed."),
    FeatureField("pitcher_whiff_rate", "pitcherSavant", "float", "Pitcher whiff rate."),
    FeatureField("pitcher_csw_rate", "pitcherSavant", "float", "Pitcher called-strike plus whiff rate."),
    FeatureField("pitcher_barrel_rate_allowed", "pitcherSavant", "float", "Pitcher barrel rate allowed."),
    FeatureField("umpire_name", "umpire", "string", "Projected or assigned home-plate umpire."),
    FeatureField("umpire_k_boost", "umpire", "float", "Historical strikeout environment adjustment."),
    FeatureField("umpire_run_environment", "umpire", "float", "Historical run environment adjustment."),
    FeatureField("hit_rate_5", "history", "float", "Recent hit rate over 5 games."),
    FeatureField("hit_rate_10", "history", "float", "Recent hit rate over 10 games."),
    FeatureField("hit_rate_20", "history", "float", "Recent hit rate over 20 games."),
    FeatureField("source_snapshot_at", "trust", "datetime", "Source collection timestamp."),
    FeatureField("source_freshness_minutes", "trust", "float", "Age of source data in minutes."),
    FeatureField("missing_feature_groups", "trust", "json", "Feature groups absent at prediction time."),
    FeatureField("actual_value", "labels", "float", "Settled player/game outcome.", pregame_safe=False),
    FeatureField("result", "labels", "string", "Win/loss/push/void label.", pregame_safe=False),
    FeatureField("hit", "labels", "bool", "Binary hit target for model training.", pregame_safe=False),
    FeatureField("graded_at", "labels", "datetime", "Post-game grading timestamp.", pregame_safe=False),
    FeatureField("closing_line_value", "labels", "float", "Post-collection CLV metric.", pregame_safe=False),
)


def fields_for_group(group: str) -> list[FeatureField]:
    return [field for field in FEATURE_FIELDS if field.group == group]


def grouped_feature_fields() -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for field in FEATURE_FIELDS:
        groups.setdefault(field.group, []).append(asdict(field))
    return groups


def pregame_feature_names() -> list[str]:
    return [field.name for field in FEATURE_FIELDS if field.pregame_safe]


def postgame_label_names() -> list[str]:
    return [field.name for field in FEATURE_FIELDS if not field.pregame_safe]


def feature_store_contract() -> dict[str, object]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "fieldCount": len(FEATURE_FIELDS),
        "pregameSafeFieldCount": len(pregame_feature_names()),
        "postgameLabelFieldCount": len(postgame_label_names()),
        "groups": grouped_feature_fields(),
        "leakagePolicy": {
            "predictionFieldsRequirePregameSafe": True,
            "labelsPregameSafe": False,
            "postgameFieldsAllowedForTrainingOnly": True,
        },
    }
