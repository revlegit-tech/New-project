from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictResponse(BaseModel):
    """Strict FastAPI response base for native production contracts."""

    model_config = ConfigDict(extra="forbid")


class StrictPayload(BaseModel):
    """Strict nested payload base for canonical native API objects."""

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(StrictResponse):
    status: str = "error"
    code: str
    message: str
    error: str | None = None
    requestId: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class EdgeBoardRow(StrictPayload):
    """Canonical row contract for board-like native responses.

    Some values are still strings because the existing CSV/source rows preserve
    raw sportsbook/source values. The contract is intentionally explicit even
    where values remain flexible during migration.
    """

    propKey: str = ""
    id: str | None = None
    date: str | None = None
    playerId: str | None = None
    player: str = ""
    team: str = ""
    opponent: str = ""
    pitcher: str | None = None
    market: str = ""
    marketDisplay: str | None = None
    baseMarket: str | None = None
    originalMarket: str | None = None
    marketFamily: str | None = None
    rawLabel: str | None = None
    rawPlayerName: str | None = None
    cleanedPlayerName: str | None = None
    cleanedPlayer: str | None = None
    playerDisplayName: str | None = None
    sourceTeam: str | None = None
    sourceOpponent: str | None = None
    resolvedTeam: str | None = None
    resolvedOpponent: str | None = None
    resolvedTeamAbbr: str | None = None
    resolvedOpponentAbbr: str | None = None
    resolvedGameId: str | None = None
    attributionCorrectionApplied: bool | None = None
    attributionCorrectionReason: str | None = None
    originalTeam: str | None = None
    originalOpponent: str | None = None
    correctedTeam: str | None = None
    correctedOpponent: str | None = None
    playerTeamEvidenceStatus: str | None = None
    rosterEvidenceAvailable: bool | None = None
    rosterMatchStatus: str | None = None
    playerTeamEvidenceSources: list[str] = Field(default_factory=list)
    playerTeamEvidenceWarnings: list[str] = Field(default_factory=list)
    attributionConfidence: str | None = None
    attributionStatus: str | None = None
    attributionWarnings: list[str] = Field(default_factory=list)
    attributionSources: list[str] = Field(default_factory=list)
    teamVerified: bool | None = None
    opponentVerified: bool | None = None
    playerVerified: bool | None = None
    attributionConflictReason: str | None = None
    contextBlockedByAttribution: bool | None = None
    contextAllowedWithWarning: bool | None = None
    identityConfidence: str | None = None
    identityWarnings: list[str] = Field(default_factory=list)
    playerTeamVerified: bool | None = None
    side: str | None = None
    line: Any = None
    book: str | None = None
    bookKey: str | None = None
    bookCount: Any = None
    books: list[Any] = Field(default_factory=list)
    propId: str | None = None
    normalizedPropKey: str | None = None
    gameId: str | None = None
    normalizedPlayer: str | None = None
    decimalOdds: Any = None
    impliedProbability: Any = None
    noVigImpliedProbability: Any = None
    lastUpdate: str | None = None
    quoteFreshness: str | None = None
    selectedBook: str | None = None
    selectedBookAmericanOdds: Any = None
    selectedBookImpliedProbability: Any = None
    selectedBookLastUpdate: str | None = None
    selectedBookQuoteStatus: str | None = None
    selectedBookMode: str | None = None
    bestBook: str | None = None
    bestAmericanOdds: Any = None
    bestImpliedProbability: Any = None
    bestBookLastUpdate: str | None = None
    quoteCount: Any = None
    availableBooks: list[Any] = Field(default_factory=list)
    allBookQuotes: list[Any] = Field(default_factory=list)
    quoteHydrationWarning: str | None = None
    quoteDetailUnavailable: bool | None = None
    americanOdds: Any = None
    rawModelProbability: Any = None
    calibratedProbability: Any = None
    calibrationApplied: bool | None = None
    calibrationMethod: str | None = None
    calibrationArtifactGeneratedAt: str | None = None
    modelQualityWarnings: list[str] = Field(default_factory=list)
    modelProbabilityPercent: Any = None
    impliedProbabilityPercent: Any = None
    edgePercent: Any = None
    fairOdds: Any = None
    expectedValue: Any = None
    finalProbabilityPercent: Any = None
    sportsbookImpliedPercent: Any = None
    finalEdgePercent: Any = None
    confidence: str | None = None
    recommendation: str | None = None
    weatherAdjustmentPercent: Any = None
    savantAdjustmentPercent: Any = None
    oddsMovementAdjustmentPercent: Any = None
    missingData: list[Any] = Field(default_factory=list)
    hitRates: dict[str, Any] = Field(default_factory=dict)
    recentGames: list[dict[str, Any]] = Field(default_factory=list)
    rank: int | None = None
    gameTime: str | None = None
    readinessLabel: str = ""
    modelReadiness: Any = None
    decisionLabel: str = ""
    action: str | None = None
    actionLabel: str | None = None
    decisionTone: str | None = None
    marketCapabilityStatus: str | None = None
    modelProductionEligible: bool | None = None
    productionStatus: str | None = None
    canShowConfidentPick: bool | None = None
    trainingRows: Any = None
    positiveRows: Any = None
    negativeRows: Any = None
    latestGradedDate: str | None = None
    calibrationStatus: str | None = None
    backtestStatus: str | None = None
    missingFeatureGroups: list[str] = Field(default_factory=list)
    missingDataCount: int | None = None
    missingDataSummary: str | None = None
    productionEligibleReason: str | None = None
    actionabilityReason: str | None = None
    productionGateStatus: str | None = None
    productionGateReasons: list[str] = Field(default_factory=list)
    productionEligible: bool | None = None
    betActionAllowed: bool | None = None
    warningCount: int | None = None
    trustWarnings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    suggestedStake: str | None = None
    stakeUnits: Any = None
    predictionMatched: bool | None = None
    predictionKey: str | None = None
    predictionSource: str | None = None
    predictionWarnings: list[str] = Field(default_factory=list)
    modelCard: dict[str, Any] = Field(default_factory=dict)
    trust: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
    isAltMarket: bool | str | None = None
    game_market_available: bool | None = None
    game_market_game_id: str | None = None
    game_market_consensus_open_total: Any = None
    game_market_consensus_current_total: Any = None
    game_market_total_line_movement: Any = None
    game_market_favorite_team_open: str | None = None
    game_market_favorite_team_current: str | None = None
    game_market_team_is_favorite_open: bool | None = None
    game_market_team_is_favorite_current: bool | None = None
    game_market_team_no_vig_win_prob_open: Any = None
    game_market_team_no_vig_win_prob_current: Any = None
    game_market_opponent_no_vig_win_prob_open: Any = None
    game_market_opponent_no_vig_win_prob_current: Any = None
    game_market_book_count_moneyline: Any = None
    game_market_book_count_total: Any = None
    game_market_book_count_runline: Any = None
    game_market_disagreement_score: Any = None
    game_market_team_moneyline_movement: Any = None
    game_market_opponent_moneyline_movement: Any = None
    game_market_quality_flags: list[str] = Field(default_factory=list)
    game_market_enrichment_status: str | None = None


class ModelCardItem(StrictPayload):
    market: str = ""
    marketName: str | None = None
    version: str | None = None
    status: str | None = None
    modelStatus: str | None = None
    productionStatus: str | None = None
    readinessLabel: str | None = None
    canShowConfidentPick: bool | None = None
    reason: str | None = None
    trainingRows: int | None = None
    positiveRows: int | None = None
    negativeRows: int | None = None
    classCounts: dict[str, Any] = Field(default_factory=dict)
    trainedAt: str | None = None
    latestGradedDate: str | None = None
    artifactExists: bool | None = None
    metadataExists: bool | None = None
    artifact: str | None = None
    artifactSha256: str | None = None
    artifactHashPrefix: str | None = None
    featuresSha256: str | None = None
    metricsSha256: str | None = None
    hashVerified: bool | None = None
    artifactVerification: dict[str, Any] = Field(default_factory=dict)
    featureSchema: dict[str, Any] = Field(default_factory=dict)
    calibrated: bool | None = None
    calibration: dict[str, Any] = Field(default_factory=dict)
    backtest: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    trainingWindow: dict[str, Any] = Field(default_factory=dict)
    lastPromotedAt: str | None = None
    knownLimitations: list[str] = Field(default_factory=list)
    researchOnly: bool | None = None
    productionReady: bool | None = None
    trustWarnings: list[str] = Field(default_factory=list)
    decisionPolicy: dict[str, Any] = Field(default_factory=dict)


class ResearchLockPayload(StrictPayload):
    action: str = "Research"
    readinessLabel: str = "Experimental"
    stakeUnits: int | float = 0
    betActionAllowed: bool = False


class MarketRegistryItem(StrictPayload):
    marketKey: str = ""
    displayName: str = ""
    category: str = ""
    propType: str = ""
    sideType: str = ""
    hasOdds: bool = False
    hasModel: bool = False
    hasAltLines: bool = False
    rowCount: int = 0
    quoteCount: int = 0
    availableBooks: list[str] = Field(default_factory=list)
    supportedInBoard: bool = False
    supportedInReport: bool = False
    supportedInModel: bool = False
    modelStatus: str = ""
    warning: str = ""
    warnings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    missingModelMarket: bool = False
    modelUnavailable: bool = False
    hidden: bool = False
    hiddenReason: str = ""
    badges: list[str] = Field(default_factory=list)
    sortableFields: list[str] = Field(default_factory=list)
    marketSupportsModelSort: bool = False
    marketSupportsOddsSort: bool = False
    marketSupportsEdgeSort: bool = False
    marketSupportsLineSort: bool = False


class MarketRegistryGroup(StrictPayload):
    key: str = ""
    label: str = ""
    markets: list[MarketRegistryItem] = Field(default_factory=list)
    rowCount: int = 0
    quoteCount: int = 0


class MarketCoverageDiagnostics(StrictPayload):
    rawPropsPulled: int = 0
    rawBookQuotesPulled: int = 0
    uniquePropIdentities: int = 0
    uniqueBookQuotes: int = 0
    playerboardCardsBuilt: int = 0
    boardRowsVisible: int = 0
    cardsCollapsedByBook: int = 0
    cardsCollapsedBySide: int = 0
    cardsCollapsedByLine: int = 0
    cardsCollapsedByMarket: int = 0
    cardsCollapsedByPlayer: int = 0
    duplicateQuoteRows: int = 0
    duplicatePropIdentityRows: int = 0
    unsupportedMarketRows: int = 0
    unsupportedBookRows: int = 0
    missingPlayerRows: int = 0
    missingTeamRows: int = 0
    missingOddsRows: int = 0
    marketsFound: int = 0
    marketsDiscoveredFromPropLine: list[str] = Field(default_factory=list)
    marketsDiscoveredFromActionNetwork: list[str] = Field(default_factory=list)
    marketsDiscoveredFromPlayerboard: list[str] = Field(default_factory=list)
    marketsWithRows: list[str] = Field(default_factory=list)
    marketsShownInDropdown: list[str] = Field(default_factory=list)
    marketsHiddenFromDropdown: list[str] = Field(default_factory=list)
    marketsWithOddsButNoModel: list[str] = Field(default_factory=list)
    marketsWithModelButNoOdds: list[str] = Field(default_factory=list)
    altMarketsFound: list[str] = Field(default_factory=list)
    gameMarketsFound: list[str] = Field(default_factory=list)
    teamMarketsFound: list[str] = Field(default_factory=list)
    firstFiveMarketsFound: list[str] = Field(default_factory=list)
    moneylineRowsLoaded: int = 0
    runLineRowsLoaded: int = 0
    totalsRowsLoaded: int = 0
    teamTotalsRowsLoaded: int = 0
    f5RowsLoaded: int = 0
    propsDroppedByUnsupportedMarket: int = 0
    propsDroppedByUnsupportedSide: int = 0
    unknownMarketsFound: list[str] = Field(default_factory=list)
    sampleUnknownMarkets: list[str] = Field(default_factory=list)
    sampleHiddenMarkets: list[dict[str, Any]] = Field(default_factory=list)
    rowsByMarket: dict[str, int] = Field(default_factory=dict)
    quoteCountByMarket: dict[str, int] = Field(default_factory=dict)
    booksByMarket: dict[str, list[str]] = Field(default_factory=dict)
    modelSupportStatus: dict[str, str | None] = Field(default_factory=dict)
    oddsOnlyMarketCount: int = 0
    missingModelMarketCount: int = 0
    warnings: list[str] = Field(default_factory=list)


class MarketRegistryResponse(StrictResponse):
    status: str = "ok"
    date: str = ""
    season: int | None = None
    markets: list[MarketRegistryItem] = Field(default_factory=list)
    groups: list[MarketRegistryGroup] = Field(default_factory=list)
    marketCoverage: MarketCoverageDiagnostics = Field(default_factory=MarketCoverageDiagnostics)
    coverage: MarketCoverageDiagnostics | None = None
    sortableFields: list[str] = Field(default_factory=list)
    defaultSort: str = ""
    researchLock: ResearchLockPayload = Field(default_factory=ResearchLockPayload)


class PickItem(StrictPayload):
    id: str = ""
    status: str = ""
    source: str | None = None
    date: str | None = None
    player: str | None = None
    team: str | None = None
    opponent: str | None = None
    market: str | None = None
    marketDisplay: str | None = None
    side: str | None = None
    line: Any = None
    book: str | None = None
    americanOdds: Any = None
    confidence: str | None = None
    notes: str | None = None
    warnings: list[str] = Field(default_factory=list)
    createdAt: str | None = None
    updatedAt: str | None = None
    stakeUnits: float | None = None
    stakeAmount: float | None = None
    decisionLabel: str | None = None
    readinessLabel: str | None = None
    modelProbabilityPercent: Any = None
    impliedProbabilityPercent: Any = None
    edgePercent: Any = None
    latestGradedDate: str | None = None
    suggestedStake: str | None = None
    profitUnits: float | None = None
    gameKey: str | None = None


class ExposureSummaryPayload(StrictPayload):
    activePickCount: int = 0
    totalStakeUnits: float = 0.0
    totalStakeAmount: float = 0.0
    byGameUnits: list[dict[str, Any]] = Field(default_factory=list)
    byPlayerUnits: list[dict[str, Any]] = Field(default_factory=list)
    byMarketUnits: list[dict[str, Any]] = Field(default_factory=list)
    settledPickCount: int = 0
    profitUnits: float = 0.0
    profitAmount: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    caps: dict[str, Any] = Field(default_factory=dict)


class PropDetailPayload(StrictPayload):
    id: str | None = None
    propKey: str | None = None
    overview: dict[str, Any] = Field(default_factory=dict)
    priceComparison: dict[str, Any] = Field(default_factory=dict)
    modelExplanation: dict[str, Any] = Field(default_factory=dict)
    playerContext: dict[str, Any] = Field(default_factory=dict)
    trendProfile: dict[str, Any] = Field(default_factory=dict)
    gameContext: dict[str, Any] = Field(default_factory=dict)
    riskContext: dict[str, Any] = Field(default_factory=dict)
    tracking: dict[str, Any] = Field(default_factory=dict)


class DataHealthResponse(StrictResponse):
    schemaVersion: str | None = None
    date: str | None = None
    season: int | str | None = None
    dataRoot: str | None = None
    latestLocalSummary: dict[str, Any] = Field(default_factory=dict)
    latestCloudRun: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, Any] = Field(default_factory=dict)
    timestamps: dict[str, Any] = Field(default_factory=dict)
    savant: dict[str, Any] = Field(default_factory=dict)
    batterVsPitcher: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    ok: bool | None = None
    grading: dict[str, Any] = Field(default_factory=dict)
    productState: dict[str, Any] = Field(default_factory=dict)
    latestFullyGradedDate: str | None = None
    trust: dict[str, Any] = Field(default_factory=dict)


class DataHealthDashboardResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    ok: bool | None = None
    version: str | None = None
    season: int | str | None = None
    date: str | None = None
    generatedAt: str | None = None
    overallStatus: str | None = None
    dataConfidence: str | None = None
    productState: dict[str, Any] = Field(default_factory=dict)
    latestBoardDate: str | None = None
    latestFullyGradedDate: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    cards: list[dict[str, Any]] = Field(default_factory=list)
    workflowPhases: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    advancedLinks: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class CollectorManifestPayload(StrictPayload):
    run_id: str = ""
    date: str = ""
    run_type: str = ""
    started_at: str = ""
    finished_at: str = ""
    success: bool = False
    requested_markets: list[str] = Field(default_factory=list)
    source_counts: dict[str, int] = Field(default_factory=dict)
    market_counts: dict[str, int] = Field(default_factory=dict)
    playerboard_rows: int = 0
    edge_board_rows: int | None = None
    raw_files_written: list[str] = Field(default_factory=list)
    normalized_files_written: list[str] = Field(default_factory=list)
    warehouse_files_written: list[str] = Field(default_factory=list)
    artifact_critical_files_present: list[str] = Field(default_factory=list)
    artifact_critical_files_missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    traceback_tail: str = ""
    freshness_status: str = "missing"


class DataSourceFreshnessPayload(StrictPayload):
    status: str
    path: str
    latest_file: str | None = None
    latest_timestamp: str | None = None
    age_seconds: int | None = None
    row_count: int | None = None
    file_count: int = 0
    market_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DataStatusResponse(StrictResponse):
    schemaVersion: str | None = None
    status: str
    current_date: str
    generated_at: str
    latest_collector_manifest: CollectorManifestPayload | None = None
    source_freshness: dict[str, DataSourceFreshnessPayload] = Field(default_factory=dict)
    database: dict[str, Any] = Field(default_factory=dict)
    historical_game_odds: dict[str, Any] = Field(default_factory=dict)
    game_market_enrichment: dict[str, Any] = Field(default_factory=dict)
    ml_feature_exports: dict[str, Any] = Field(default_factory=dict)
    ml_label_exports: dict[str, Any] = Field(default_factory=dict)
    ml_training_datasets: dict[str, Any] = Field(default_factory=dict)
    expected_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_health_score: int = Field(ge=0, le=100)


class HistoricalGameOddsImportResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    importStatus: str = ""
    importId: str = ""
    sourceFile: str = ""
    startedAt: str = ""
    finishedAt: str = ""
    gamesRead: int = 0
    gamesImported: int = 0
    lineRowsImported: int = 0
    featureRowsWritten: int = 0
    gradeRowsWritten: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    csvExports: dict[str, str] = Field(default_factory=dict)


class HistoricalGameOddsStatusResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    enabled: bool = False
    reachable: bool = False
    dialect: str = ""
    reason: str = ""
    error: str = ""
    games: int = 0
    lineRows: int = 0
    featureRows: int = 0
    gradeRows: int = 0
    latestImportAt: str = ""
    latestImportStatus: str = ""
    sourceFilePresent: bool = False
    warnings: list[str] = Field(default_factory=list)


class HistoricalGameOddsRowsResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    date: str = ""
    rowCount: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MLFeatureStatusResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    enabled: bool = True
    feature_schema_version: str = ""
    database: dict[str, Any] = Field(default_factory=dict)
    latest_export_date: str = ""
    latest_export_row_count: int = 0
    safe_feature_count: int = 0
    blocked_feature_count: int = 0
    game_market_feature_availability: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MLFeatureExportResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    feature_schema_version: str = ""
    exported_at: str = ""
    date: str = ""
    season: int = 0
    source: str = ""
    format: str = ""
    dry_run: bool = False
    row_count: int = 0
    raw_row_count: int = 0
    market_counts: dict[str, int] = Field(default_factory=dict)
    source_counts: dict[str, int] = Field(default_factory=dict)
    safe_feature_count: int = 0
    blocked_feature_count: int = 0
    export_column_count: int = 0
    game_market_match_count: int = 0
    game_market_missing_count: int = 0
    game_market_coverage_pct: float = 0.0
    leakage_blocked_fields: list[str] = Field(default_factory=list)
    leakage_blocked_field_count: int = 0
    leakage_check_passed: bool = True
    output_paths: dict[str, str] = Field(default_factory=dict)
    written: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MLFeaturePreviewResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    feature_schema_version: str = ""
    date: str = ""
    row_count: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BacktestReadinessResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    feature_schema_version: str = ""
    date: str = ""
    source: str = ""
    market_count: int = 0
    markets: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MLLabelStatusResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    enabled: bool = True
    label_schema_version: str = ""
    latest_label_date: str = ""
    latest_label_rows: int = 0
    latest_training_date: str = ""
    latest_training_rows: int = 0
    supported_markets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlayerPropLabelBuildResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    label_schema_version: str = ""
    date: str = ""
    season: int = 0
    source: str = ""
    format: str = ""
    dry_run: bool = False
    row_count: int = 0
    feature_row_count: int = 0
    graded_count: int = 0
    ungraded_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    push_count: int = 0
    void_count: int = 0
    market_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    supported_market_count: int = 0
    unsupported_market_count: int = 0
    output_paths: dict[str, str] = Field(default_factory=dict)
    written: bool = False
    warnings: list[str] = Field(default_factory=list)


class PlayerPropLabelPreviewResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    label_schema_version: str = ""
    date: str = ""
    row_count: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlayerPropTrainingBuildResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    feature_schema_version: str = ""
    label_schema_version: str = ""
    training_schema_version: str = ""
    date: str = ""
    season: int = 0
    source: str = ""
    format: str = ""
    dry_run: bool = False
    feature_row_count: int = 0
    label_row_count: int = 0
    joined_row_count: int = 0
    graded_training_row_count: int = 0
    ungraded_training_row_count: int = 0
    market_counts: dict[str, int] = Field(default_factory=dict)
    result_counts: dict[str, int] = Field(default_factory=dict)
    label_status_counts: dict[str, int] = Field(default_factory=dict)
    feature_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    metadata_columns: list[str] = Field(default_factory=list)
    leakage_check_passed: bool = True
    blocked_feature_fields_found: list[str] = Field(default_factory=list)
    output_paths: dict[str, str] = Field(default_factory=dict)
    written: bool = False
    warnings: list[str] = Field(default_factory=list)


class PlayerPropTrainingPreviewResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    training_schema_version: str = ""
    feature_schema_version: str = ""
    label_schema_version: str = ""
    date: str = ""
    row_count: int = 0
    feature_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)
    metadata_columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GradingHealthResponse(StrictResponse):
    schemaVersion: str | None = None
    state: str
    ok: bool
    date: str = ""
    latestFullyGradedDate: str = ""
    checkedAt: str = ""
    file: str = ""
    exists: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    requestedDate: str = ""


class WorkflowHealthResponse(StrictResponse):
    schemaVersion: str | None = None
    ok: bool
    healthDir: str
    summaries: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PropMlStatusResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    mode: str | None = None
    markets: list[dict[str, Any]] = Field(default_factory=list)
    readyMarkets: list[str] = Field(default_factory=list)
    notReadyMarkets: list[str] = Field(default_factory=list)
    trainedMarkets: list[str] = Field(default_factory=list)
    productionEligibleMarkets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    marketsWithHashIssues: list[str] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)


class MLModelsStatusResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    registry: dict[str, Any] = Field(default_factory=dict)
    modelCounts: dict[str, int] = Field(default_factory=dict)
    markets: list[str] = Field(default_factory=list)
    productionMarkets: list[str] = Field(default_factory=list)
    shadowMarkets: list[str] = Field(default_factory=list)
    candidateMarkets: list[str] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MLModelsRegistryResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    entries: list[dict[str, Any]] = Field(default_factory=list)
    entryCount: int = 0
    markets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MLModelsMetricsResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    metricCount: int = 0
    warnings: list[str] = Field(default_factory=list)


class MLModelsFeatureCoverageResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    entryCount: int = 0
    receivedFeatureCount: int = 0
    warnings: list[str] = Field(default_factory=list)


class MLModelsPredictionPreviewResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    preview: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MLModelsAdminActionResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    action: str = ""
    market: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class MetricsSeries(StrictPayload):
    name: str
    labels: dict[str, Any] = Field(default_factory=dict)
    value: float | None = None
    count: int | None = None
    min: float | None = None
    max: float | None = None
    avg: float | None = None
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None


class ObservabilityMetricsResponse(StrictResponse):
    status: str = "ok"
    counters: list[MetricsSeries] = Field(default_factory=list)
    histograms: list[MetricsSeries] = Field(default_factory=list)
    gauges: list[MetricsSeries] = Field(default_factory=list)


class AppStatusResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    ok: bool | None = None
    season: int | None = None
    warnings: list[str] = Field(default_factory=list)
    checkedAt: str | None = None
    generatedAt: str | None = None
    productState: str | None = None
    productStateDetail: dict[str, Any] = Field(default_factory=dict)
    latestFullyGradedDate: str | None = None
    latestBoardDate: str | None = None
    researchMode: bool | None = None
    trainedMarkets: list[str] = Field(default_factory=list)
    productionEligibleMarkets: list[str] = Field(default_factory=list)
    dataConfidence: str | None = None
    dataConfidenceDetail: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    modelReadiness: dict[str, Any] = Field(default_factory=dict)
    modelPolicy: dict[str, Any] = Field(default_factory=dict)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    alertCount: int | None = None
    observability: dict[str, Any] = Field(default_factory=dict)
    playerboard: dict[str, Any] = Field(default_factory=dict)
    grading: dict[str, Any] = Field(default_factory=dict)
    workflows: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    snapshotAgeSeconds: float | None = None
    boardCacheStatus: dict[str, Any] = Field(default_factory=dict)
    contractErrors: list[str] = Field(default_factory=list)


class CollectorCheckResponse(StrictResponse):
    schemaVersion: str = "collector-check.v1"
    status: str
    date: str
    season: int
    resolvedDateMode: str
    checks: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    capabilitySummary: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class DailyHealthResponse(StrictResponse):
    schemaVersion: str = "daily-health.v1"
    date: str
    season: int
    overallStatus: str
    servingSafe: bool
    boardAvailable: bool
    featureStoreAvailable: bool
    modelReadinessAvailable: bool
    productionTrainingReady: bool = False
    scheduledCollectorStatus: str = "unknown"
    weeklyRepairStatus: str = "unknown"
    stages: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    modelTrainingTriggered: bool = False
    externalApiCallsMade: bool = False


class DataSourceCapabilityResponse(StrictResponse):
    schemaVersion: str = "data-source-capability.v1"
    status: str
    season: int
    date: str
    resolvedDateMode: str = ""
    sources: dict[str, Any] = Field(default_factory=dict)
    featureGroups: dict[str, Any] = Field(default_factory=dict)
    featureStoreContract: dict[str, Any] = Field(default_factory=dict)
    featureAudit: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class FeatureStoreMaterializerResponse(StrictResponse):
    schemaVersion: str = "feature-store-materializer.v1"
    status: str = "partial"
    date: str
    season: int
    resolvedDateMode: str = ""
    rows: int = 0
    path: str = ""
    pregameSafe: bool = True
    labelsExcluded: bool = True
    missingFeatureGroups: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    externalApiCallsMade: bool = False
    modelTrainingTriggered: bool = False


class AsofFeatureAuditResponse(StrictResponse):
    schemaVersion: str = "asof-feature-audit.v1"
    status: str = "ok"
    date: str
    season: int
    resolvedDateMode: str = ""
    pregameSafe: bool = True
    labelsSeparated: bool = True
    blockedFieldsFound: list[str] = Field(default_factory=list)
    missingFeatureGroups: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    featureMatrix: dict[str, Any] = Field(default_factory=dict)
    sourceTimestampAudit: dict[str, Any] = Field(default_factory=dict)
    externalApiCallsMade: bool = False
    modelTrainingTriggered: bool = False


class ModelTrainingReadinessResponse(StrictResponse):
    schemaVersion: str = "model-training-readiness.v1"
    status: str = "ok"
    date: str
    season: int
    resolvedDateMode: str = ""
    readyForBaselineTraining: bool = False
    readyForProductionTraining: bool = False
    eligibleBaselineMarkets: list[str] = Field(default_factory=list)
    eligibleProductionMarkets: list[str] = Field(default_factory=list)
    modelTrainingTriggered: bool = False
    externalApiCallsMade: bool = False
    xgboostAvailable: bool = False
    modelState: str = "research_only"
    allowedModelStates: list[str] = Field(default_factory=list)
    featureMatrix: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    labelArtifacts: list[str] = Field(default_factory=list)
    markets: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BaselineModelStatusResponse(StrictResponse):
    schemaVersion: str = "baseline-model-status.v1"
    date: str
    season: int
    market: str
    modelState: str = "unavailable"
    artifactExists: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)
    modelTrainingTriggered: bool = False
    externalApiCallsMade: bool = False
    readyForProductionTraining: bool = False
    warnings: list[str] = Field(default_factory=list)


class ModelCalibrationStatusResponse(StrictResponse):
    schemaVersion: str = "model-calibration-status.v1"
    date: str
    season: int
    market: str
    artifactExists: bool = False
    calibrationStatus: str = "missing"
    metrics: dict[str, Any] = Field(default_factory=dict)
    modelTrainingTriggered: bool = False
    externalApiCallsMade: bool = False
    warnings: list[str] = Field(default_factory=list)


class ModelBacktestStatusResponse(StrictResponse):
    schemaVersion: str = "model-backtest-status.v1"
    date: str
    season: int
    market: str
    artifactExists: bool = False
    backtestStatus: str = "missing"
    metrics: dict[str, Any] = Field(default_factory=dict)
    modelTrainingTriggered: bool = False
    externalApiCallsMade: bool = False
    warnings: list[str] = Field(default_factory=list)


class EdgeBoardResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    version: str | None = None
    season: int | None = None
    date: str | None = None
    rows: list[EdgeBoardRow] = Field(default_factory=list)
    top: list[EdgeBoardRow] = Field(default_factory=list)
    rowCount: int | None = None
    latestFullyGradedDate: str | None = None
    productState: dict[str, Any] | str | None = None
    modelReadiness: dict[str, Any] = Field(default_factory=dict)
    boardCache: dict[str, Any] = Field(default_factory=dict)
    cacheHit: bool | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    trust: dict[str, Any] = Field(default_factory=dict)
    dataConfidence: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
    marketRegistry: MarketRegistryResponse | None = None
    marketCoverage: MarketCoverageDiagnostics | None = None


class ResearchReportCard(StrictPayload):
    id: str = ""
    propKey: str = ""
    player: str = ""
    team: str = ""
    opponent: str = ""
    matchup: str = ""
    market: str = ""
    marketDisplay: str = ""
    side: str = ""
    line: Any = None
    americanOdds: Any = None
    book: str = ""
    score: int = 0
    grade: str = ""
    riskBucket: str = ""
    confidence: str = ""
    edgePercent: float = 0.0
    modelProbabilityPercent: float | None = None
    impliedProbabilityPercent: float | None = None
    decisionLabel: str = ""
    actionLabel: str | None = None
    readinessLabel: str = ""
    marketCapabilityStatus: str | None = None
    modelProductionEligible: bool | None = None
    calibrationStatus: str | None = None
    backtestStatus: str | None = None
    missingDataCount: int | None = None
    warningCount: int | None = None
    productionEligibleReason: str | None = None
    actionabilityReason: str | None = None
    suggestedStake: str = ""
    sourceRowRank: int = 0
    freshness: dict[str, Any] = Field(default_factory=dict)
    trust: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    gameMarketContext: dict[str, Any] = Field(default_factory=dict)


class ResearchReportSection(StrictPayload):
    key: str
    title: str
    description: str = ""
    publishTier: str = "premium"
    cardCount: int = 0
    cards: list[ResearchReportCard] = Field(default_factory=list)
    emptyState: str = ""


class ResearchReportResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    version: str | None = None
    date: str | None = None
    season: int | None = None
    product: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    sections: list[ResearchReportSection] = Field(default_factory=list)
    pricing: dict[str, Any] = Field(default_factory=dict)
    publishPlan: list[dict[str, Any]] = Field(default_factory=list)
    trust: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
    gameMarketEnrichment: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class PlayerboardResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    season: int | None = None
    date: str | None = None
    rows: list[EdgeBoardRow] = Field(default_factory=list)
    message: str | None = None
    market: str | None = None
    cardsBuilt: int | None = None
    propsLoaded: int | None = None
    saved: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    latestFullyGradedDate: str | None = None
    modelReadiness: dict[str, Any] = Field(default_factory=dict)
    cacheHit: bool | None = None
    top: list[EdgeBoardRow] = Field(default_factory=list)
    trust: dict[str, Any] = Field(default_factory=dict)
    productState: dict[str, Any] | str | None = None
    dataConfidence: str | None = None
    source: dict[str, Any] | str | None = None
    sourceMeta: dict[str, Any] = Field(default_factory=dict)
    sourceMode: str | None = None
    canonicalSourceFiles: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
    marketRegistry: MarketRegistryResponse | None = None
    marketCoverage: MarketCoverageDiagnostics | None = None


class PlayerboardHealthResponse(StrictResponse):
    status: str | None = None
    schemaVersion: str | None = None
    season: int | None = None
    ok: bool | None = None
    schemaOk: bool | None = None
    rowsLoaded: int | None = None
    totalRowsInFile: int | None = None
    latestAvailableDate: str | None = None
    latestSnapshotAt: str | None = None
    dateRowsInFile: int | None = None
    snapshotGroupCount: int | None = None
    snapshotGroups: list[str] = Field(default_factory=list)
    latestRecentGameDate: str | None = None
    recentGamesAgeDays: int | None = None
    rowsWithRecentGames: int | None = None
    staleRecentGameRows: int | None = None
    warnings: list[str] = Field(default_factory=list)
    requestedDate: str | None = None
    date: str | None = None
    market: str | None = None
    exists: bool | None = None
    file: str | None = None
    schemaIssue: str | None = None
    expectedColumnCount: int | None = None
    expectedColumns: list[str] = Field(default_factory=list)
    availableDates: list[str] = Field(default_factory=list)
    snapshots: list[Any] = Field(default_factory=list)
    marketsPresent: list[str] | dict[str, Any] = Field(default_factory=list)
    missingMarketDisplayRows: int | None = None
    sampleMissingMarketDisplayRows: list[dict[str, Any]] = Field(default_factory=list)
    badShiftedRows: int | None = None
    sampleBadRows: list[dict[str, Any]] = Field(default_factory=list)
    schemaValidation: dict[str, Any] = Field(default_factory=dict)
    slateStatus: dict[str, Any] = Field(default_factory=dict)
    usedLatestAvailableDate: bool | None = None
    productState: dict[str, Any] | str | None = None
    modelReadiness: dict[str, Any] = Field(default_factory=dict)
    grading: dict[str, Any] = Field(default_factory=dict)
    dataConfidence: str | None = None
    latestFullyGradedDate: str | None = None
    trust: dict[str, Any] = Field(default_factory=dict)
    marketRegistry: MarketRegistryResponse | None = None
    marketCoverage: MarketCoverageDiagnostics | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    freshness: dict[str, Any] = Field(default_factory=dict)
    gameMarketEnrichment: dict[str, Any] = Field(default_factory=dict)


class PropDetailResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    prop: dict[str, Any] = Field(default_factory=dict)
    row: dict[str, Any] = Field(default_factory=dict)
    modelCard: dict[str, Any] = Field(default_factory=dict)
    detail: PropDetailPayload = Field(default_factory=PropDetailPayload)
    version: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ModelCardsResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    markets: list[ModelCardItem] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    modelCard: ModelCardItem | dict[str, Any] = Field(default_factory=dict)
    version: str | None = None
    policy: dict[str, Any] = Field(default_factory=dict)
    modelSnapshot: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class PredictionEventsResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    event: dict[str, Any] = Field(default_factory=dict)
    eventCount: int | None = None
    storage: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class PickResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    pick: PickItem | None = None
    picks: list[PickItem] = Field(default_factory=list)
    pickCount: int | None = None
    version: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    storage: dict[str, Any] = Field(default_factory=dict)
    lifecycle: dict[str, Any] | list[str] = Field(default_factory=dict)
    exposure: ExposureSummaryPayload = Field(default_factory=ExposureSummaryPayload)
    policy: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class BankrollSettingsResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    allowedStakingMethods: list[str] = Field(default_factory=list)
    storage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ExposureSummaryResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    exposure: ExposureSummaryPayload = Field(default_factory=ExposureSummaryPayload)
    policy: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ProplineSyncResponse(StrictResponse):
    status: str = "ok"
    schemaVersion: str | None = None
    date: str | None = None
    sport: str | None = None
    timezone: str | None = None
    markets: list[str] = Field(default_factory=list)
    eventCount: int | None = None
    totalEventCount: int | None = None
    attemptedEventCount: int | None = None
    maxEvents: int | None = None
    propCount: int | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    savedPath: str | None = None
    snapshotPath: str | None = None
    warnings: list[str] = Field(default_factory=list)
    eventErrors: list[dict[str, Any]] = Field(default_factory=list)
    emptyEvents: list[dict[str, Any]] = Field(default_factory=list)
    skippedEvents: list[dict[str, Any]] = Field(default_factory=list)
    eventsPreview: list[dict[str, Any]] = Field(default_factory=list)
    tokenGuard: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(StrictResponse):
    status: str
    ok: bool
    checks: dict[str, Any] = Field(default_factory=dict)

