# PenaltySoccer 当前能力说明

本文档基于 `master` 分支当前源码整理，目标是说明这个 fork 目前已经实现了哪些能力，哪些能力可以直接使用，哪些能力只是提供了底层工具，仍需要额外脚本或业务层组合。

## 1. 项目整体定位

当前仓库本质上是 `penaltyblog` Python 包的 fork，并在此基础上新增了一个实验脚本 `experiments/full_predict.py`。包名仍是 `penaltyblog`，版本信息在 `pyproject.toml` 中定义为 `1.11.0`，项目描述是 Football soccer Data & Modelling Made Easy。

顶层包 `penaltyblog` 当前导出了这些主要模块：`backtest`、`betting`、`fpl`、`implied`、`matchflow`、`metrics`、`models`、`ratings`、`scrapers`、`viz`、`xt`。这些模块构成了项目的主要能力边界。

项目依赖包括 `numpy`、`pandas`、`scipy`、`cython`、`requests`、`lxml`、`beautifulsoup4`、`fsspec`、`plotly`、`matplotlib`、`statsbombpy`、`pulp`、`tqdm` 等。云存储能力通过可选依赖提供，包含 `s3fs`、`gcsfs`、`adlfs`、`gcloud`。

## 2. 数据抓取能力

### 2.1 FootballData

`penaltyblog.scrapers.FootballData` 用于从 `football-data.co.uk` 抓取赛程、赛果和 CSV 中自带的统计或赔率字段。构造参数是 `competition`、`season` 和可选的 `team_mappings`。

核心方法是 `get_fixtures()`。它会根据联赛和赛季拼接类似 `https://www.football-data.co.uk/mmz4281/{season}/{competition}.csv` 的地址，读取 CSV，整理字段名，并生成统一格式的数据表。统一字段包括 `competition`、`season`、`datetime`、`date`、`team_home`、`team_away`、`goals_home`、`goals_away` 等。

这也是当前 `experiments/full_predict.py` 默认用于训练模型的主数据源。它适合快速得到历史赛果，训练 Poisson、Dixon Coles、Bivariate Poisson 等进球模型。

### 2.2 Understat

`penaltyblog.scrapers.Understat` 用于从 Understat 抓取比赛数据。它通过 `getLeagueData/{competition}/{season}` 接口获取数据，并整理为 pandas DataFrame。

`get_fixtures()` 会返回已结束比赛，包括 `understat_id`、`datetime`、`team_home`、`team_away`、`goals_home`、`goals_away`、`xg_home`、`xg_away`、`forecast_w`、`forecast_d`、`forecast_l` 等字段。

`get_shots(understat_id)` 可以进一步抓取指定比赛的射门数据。这个能力可以用于更细粒度的 xG、射门质量和机会分析。

当前 `full_predict.py` 已经调用 Understat，但只把最近 xG 表现作为上下文展示，没有把 xG 作为模型训练特征。

### 2.3 ClubElo

`penaltyblog.scrapers.ClubElo` 用于从 `api.clubelo.com` 获取球队 Elo 数据。主要方法包括 `get_elo_by_date(date=None)`、`get_elo_by_team(team)`、`get_team_names()`。

`get_elo_by_date()` 可以获取某一天所有球队的 Elo 评分。`get_elo_by_team()` 可以获取某支球队的历史 Elo。当前 `full_predict.py` 使用的是 `get_elo_by_date()`，用于展示两队 Elo 差距。

当前 ClubElo 信息同样没有进入模型训练，只作为强弱背景信息展示。

### 2.4 FBRef

`penaltyblog.scrapers.FBRef` 用于从 FBRef 抓取赛程、赛果、xG 和球队或球员统计。它内置了简单的请求间隔控制，避免请求过于频繁。

`get_fixtures()` 会抓取联赛赛程页面，整理出 `team_home`、`team_away`、`xg_home`、`xg_away`、`goals_home`、`goals_away`、`date`、`datetime` 等字段。

`get_stats(stat_type="standard")` 可以抓取球队和球员统计，返回一个字典，包含 `squad_for`、`squad_against`、`players` 三类数据。支持的统计类型由当前联赛映射决定，代码里覆盖了 standard、goalkeeping、advanced_goalkeeping、goal_shot_creation、defensive_actions、playing_time 等页面类型。

需要注意，FBRef 是网页抓取，稳定性会受到页面结构、访问限制和网络环境影响。之前全量测试中的 FBRef 报错就属于这一类外部依赖问题。

### 2.5 FPL

`penaltyblog.fpl` 模块用于抓取和处理 Fantasy Premier League API 数据。顶层 `fpl.__init__.py` 暴露了 `fpl.py` 中的全部公共内容。这个模块更偏英超 Fantasy 数据，不是当前 `full_predict.py` 的默认输入源。

## 3. MatchFlow 数据流能力

`penaltyblog.matchflow.Flow` 是一个面向 JSON 和事件数据的惰性流水线工具。它可以从文件夹、JSON、JSONL、glob、list、records 等来源创建 Flow。

数据读取支持本地路径，也支持通过 `fsspec` 访问云存储路径。代码中已经对 `s3://`、`gs://`、`gcs://`、`azure://`、`abfs://`、`abfss://` 等协议做了依赖检查。缺少对应依赖时，会提示安装 `s3fs`、`gcsfs` 或 `adlfs`。

Flow 支持的处理操作包括 `filter`、`assign`、`select`、`flatten`、`distinct`、`rename`、`group_by`、`summary`、`sort_by`、`limit`、`head`、`show`、`keys`、`drop`、`dropna`、`concat`、`explode`、`join`、`to_pandas`、`to_json`、`to_jsonl` 等。

`matchflow` 还导出了谓词辅助函数，例如 `where_equals`、`where_not_equals`、`where_in`、`where_not_in`、`where_gt`、`where_gte`、`where_lt`、`where_lte`、`where_exists`、`where_is_null`、`where_contains`、`and_`、`or_`、`not_`。同时还存在 Opta 事件和 qualifier 相关辅助函数，例如 `where_opta_event`、`where_opta_qualifier`、`get_opta_mappings`。

这部分能力适合处理事件级 JSON 数据，例如 StatsBomb、Opta 或其他提供商的数据。它本身不是比赛预测模型，而是数据清洗、转换、筛选、汇总和连接工具。

## 4. 比赛建模能力

### 4.1 基础进球模型框架

`BaseGoalsModel` 是大部分进球模型的基类。它提供输入验证、球队索引、权重数组、neutral venue 标记、模型保存和加载、统一拟合接口、AIC、log-likelihood、参数读取、单场预测和批量预测。

模型输入的核心是历史比赛中的 `goals_home`、`goals_away`、`teams_home`、`teams_away`，可选 `weights` 和 `neutral_venue`。当前这些模型没有直接接收 xG、Elo、赔率、伤停或阵容作为训练特征。

模型通过 `scipy.optimize.minimize` 优化参数。拟合后可以调用 `predict(home_team, away_team)`，返回 `FootballProbabilityGrid`。也可以用 `predict_many()` 批量预测多场比赛。

`BaseGoalsModel.save(filepath)` 和 `BaseGoalsModel.load(filepath)` 支持 pickle 持久化。这是定期重训后保存模型 bundle 的基础能力。

### 4.2 已导出的模型类型

`penaltyblog.models` 当前导出了这些主要模型和工具：

| 名称 | 用途 |
| --- | --- |
| `PoissonGoalsModel` | 基础 Poisson 进球模型 |
| `DixonColesGoalModel` | Dixon Coles 低比分修正模型 |
| `BivariatePoissonGoalModel` | 双变量 Poisson 模型 |
| `NegativeBinomialGoalModel` | 负二项进球模型，用于处理过度离散 |
| `ZeroInflatedPoissonGoalsModel` | 零膨胀 Poisson 模型 |
| `WeibullCopulaGoalsModel` | Weibull Copula 进球模型 |
| `BayesianGoalModel` | Bayesian 进球模型 |
| `HierarchicalBayesianGoalModel` | 层级 Bayesian 进球模型 |
| `FootballProbabilityGrid` | 精确比分概率矩阵和盘口概率计算工具 |
| `create_dixon_coles_grid` | Dixon Coles 概率矩阵辅助函数 |
| `goal_expectancy`、`goal_expectancy_extended` | 根据赔率或盘口反推进球期望的工具 |
| `dixon_coles_weights` | 生成 Dixon Coles 时间衰减权重 |

当前 `full_predict.py` 默认训练 `DixonColesGoalModel`、`PoissonGoalsModel`、`BivariatePoissonGoalModel` 三个模型，也预留了 `negative_binomial`、`zero_inflated`、`weibull_copula` 三个可选模型。

### 4.3 FootballProbabilityGrid 市场概率

`FootballProbabilityGrid` 是模型预测结果的核心对象。它保存精确比分概率矩阵 `P(Home goals = h, Away goals = a)`，并在同一个矩阵上计算各类市场概率。

已经实现的市场和指标包括：

| 能力 | 说明 |
| --- | --- |
| `home_win`、`draw`、`away_win` | 主胜、平局、客胜概率 |
| `home_draw_away` | `[主胜, 平局, 客胜]` 列表 |
| `btts_yes`、`btts_no` | 双方是否进球 |
| `double_chance_1x`、`double_chance_x2`、`double_chance_12` | 双重机会 |
| `draw_no_bet_home`、`draw_no_bet_away` | 平局退款条件概率 |
| `totals(line)` | 大小球概率，返回 under、push、over |
| `total_goals(over_under, strike)` | 兼容旧接口的大小球概率 |
| `asian_handicap_probs(side, line)` | 亚洲让球 win、push、lose 概率，支持整数、半球、四分之一球 |
| `asian_handicap(home_away, strike)` | 兼容旧接口的亚洲让球赢盘概率 |
| `exact_score(h, a)` | 指定比分概率 |
| `home_goal_expectation`、`away_goal_expectation` | 主客队期望进球 |

亚洲让球的标准规则是：传入 `side="home"` 时，`line < 0` 表示主队让球，`line > 0` 表示主队受让。当前 `full_predict.py` 已经改回这个标准。

## 5. Bayesian 建模能力

项目导出了 `BayesianGoalModel` 和 `HierarchicalBayesianGoalModel`。README 中也明确提到它支持 Bayesian 和 Hierarchical Bayesian 模型，能够处理参数不确定性和联赛层面的方差学习。

这部分目前没有被 `full_predict.py` 默认调用。原因是 Bayesian 模型通常计算成本更高，适合在需要后验分布、参数不确定性和更严谨统计解释时使用。后续可以单独设计脚本或命令，将 Bayesian 模型作为高成本增强模型。

## 6. 赔率和隐含概率能力

`penaltyblog.implied` 暴露 `calculate_implied`、`ImpliedMethod`、`ImpliedProbabilities`、`OddsFormat`、`OddsInput`。

`calculate_implied()` 可以把博彩公司赔率转换为隐含概率，并支持多种去水方法，包括 multiplicative、additive、power、shin、differential margin weighting、odds ratio、logarithmic 等。输入赔率可以是 decimal、American、fractional 等格式。

当前 `full_predict.py` 支持 `--odds-1x2 HOME DRAW AWAY`，用于把胜平负欧赔转为市场隐含概率，并和模型输出的胜平负概率比较。当前它只做比较，不用赔率反向修正模型概率。

## 7. 投注工具能力

`penaltyblog.betting` 提供了一组投注决策辅助工具。当前导出的主要能力包括：

| 能力 | 说明 |
| --- | --- |
| `kelly_criterion` | 单个投注 Kelly 仓位计算 |
| `multiple_kelly_criterion` | 多投注组合 Kelly 仓位计算 |
| `arbitrage_hedge` | 套利对冲计算 |
| `identify_value_bet` | 根据赔率和估计概率识别价值投注 |
| `calculate_bet_value` | 计算投注期望价值 |
| `find_arbitrage_opportunities` | 寻找套利机会 |
| `convert_odds` | 赔率格式转换 |
| `ValueBetResult`、`MultipleValueBetResult`、`ArbitrageResult` | 投注分析结果数据结构 |

`identify_value_bet()` 会比较博彩公司赔率和估计真实概率，输出隐含概率、期望价值、期望收益率、edge、是否 value bet、Kelly 推荐仓位、潜在盈亏等信息。

这部分能力当前还没有接入 `full_predict.py`。目前 `full_predict.py` 会显示模型概率和市场隐含概率差值，但尚未用 `betting` 模块计算 EV、Kelly 或 value bet 结论。

## 8. 回测能力

`penaltyblog.backtest` 提供 `Backtest`、`Account`、`Context`。

`Backtest` 接收包含 `date` 字段的数据表，并在指定日期窗口内按日期推进。每个日期会生成 `lookback` 和当天比赛。可以提供 `trainer(ctx)` 在每天训练模型，也可以提供 `logic(ctx)` 对每场比赛执行策略。

`Account` 用于模拟账户资金，`place_bet(odds, stake, outcome)` 会记录虚拟投注，更新 bankroll 和资金轨迹。

`Backtest.results()` 会输出总投注数、成功投注数、命中率、最大资金、最小资金、利润和 ROI。

这部分能力适合后续验证大小球、让球、胜平负策略是否长期有效。当前 `full_predict.py` 还没有调用 backtest 模块。

## 9. 模型评估指标能力

`penaltyblog.metrics` 导出了 `multiclass_brier_score`、`ignorance_score`、`rps_array`、`rps_average`。

这些指标可以用来评估概率预测质量。例如胜平负三分类可以使用 Brier Score、Ignorance Score 或 Ranked Probability Score。它们适合接入回测和模型比较流程。

当前 `full_predict.py` 没有接入这些指标。

## 10. 球队评级能力

`penaltyblog.ratings` 导出 `Elo`、`Massey`、`Colley`、`PiRatingSystem`。

其中 `Elo` 已实现主场优势和简单平局概率处理。它可以获取球队默认评分，计算主队胜率，计算胜平负概率，并根据赛果更新双方评分。

`Massey`、`Colley`、`PiRatingSystem` 适合从历史赛果构建不同形式的球队强弱评分。它们和 `scrapers.ClubElo` 不同，前者是本项目内部计算评级，后者是从 ClubElo 外部数据源抓取现成 Elo。

当前 `full_predict.py` 使用的是外部 `ClubElo` 数据源，没有调用内部 `ratings` 模块来训练自己的评级系统。

## 11. 可视化能力

`penaltyblog.viz` 导出 `Pitch`、`Theme`、`PitchDimensions`，以及 Bayesian 诊断相关函数 `plot_trace`、`plot_autocorr`、`plot_posterior`、`plot_convergence`、`plot_diagnostics`。

这说明项目的可视化能力主要包括两类：一类是球场和事件数据可视化，另一类是 Bayesian 模型诊断图。README 中还提到可以创建球场可视化和数据流图。

当前 `full_predict.py` 还没有图像输出。后续可以新增 `--plot-out`，把胜平负概率、大小球概率、亚洲让球概率、比分热力图画出来。

## 12. Expected Threat 能力

`penaltyblog.xt` 提供 Expected Threat 模型，包括 `XTModel`、`XTData`、`XTEventSchema`、`load_pretrained_xt`。

`XTModel` 是基于事件数据的位置价值模型。它把球场切分成网格，通过射门概率、进球概率和移动转移矩阵计算每个位置的威胁值。它可以拟合事件数据，也可以用预训练 xT 模型，支持对事件进行打分，输出 `xt_start`、`xt_end`、`xt_added` 等概念。

这个能力依赖事件级数据，例如传球、带球、射门、起终点坐标、动作是否成功。当前 `full_predict.py` 没有接入 xT。

## 13. Fantasy Premier League 能力

`penaltyblog.fpl` 用于 Fantasy Premier League 数据抓取和处理。结合项目依赖中的 `pulp`，这部分通常可以用于阵容优化、球员选择和预算约束类问题。

它不是当前比赛结果预测脚本的核心能力，也没有接入 `full_predict.py`。

## 14. 当前新增脚本 full_predict.py 的能力

`experiments/full_predict.py` 是当前 fork 中为你的预测目标新增的第一版实验入口。它不是原始 penaltyblog 的核心库文件，而是项目使用层脚本。

当前支持三个命令：

| 命令 | 功能 |
| --- | --- |
| `train` | 抓取数据、训练模型、保存模型 bundle |
| `predict` | 加载已保存模型 bundle，预测一场比赛 |
| `train-predict` | 训练模型并立即预测一场比赛 |

当前训练主数据来自 FootballData。默认模型是 Dixon Coles、Poisson、Bivariate Poisson。可通过 `--models` 选择 `negative_binomial`、`zero_inflated`、`weibull_copula` 等额外模型。

当前报告输出包括：胜平负概率、期望进球、BTTS、双重机会、大小球多盘口、亚洲让球多盘口、逐模型胜平负和精确比分、模型倾向、ClubElo 上下文、Understat 近期 xG 上下文。

当前也支持 `--odds-1x2` 输入欧赔，计算市场隐含概率和模型概率差距。

当前可以通过 `--report-out` 保存 JSON 报告。

## 15. 当前明确没有实现或没有接入的能力

以下能力目前不能视为已经完整实现：

1. `xG`、`Elo` 和赔率作为模型训练特征。当前它们只用于上下文展示或市场对比，没有进入 Poisson、Dixon Coles、Bivariate Poisson 的训练参数。
2. 伤停、阵容、首发、球员状态、未来赛程密度。当前项目没有开箱即用的伤停或阵容建模模块，也没有自动新闻抓取和阵容预测逻辑。
3. 严格赛前预测的 `cutoff-date`。当前 `full_predict.py` 使用整个指定赛季中已抓到的已完赛数据，可能包含待预测比赛之后的数据。
4. 批量预测。当前脚本一次预测一场比赛，没有读取配置文件批量输出多场报告。
5. 投注 EV 和 Kelly 建议。项目底层有 `betting` 模块，但 `full_predict.py` 还没有接入。
6. 回测闭环。项目底层有 `backtest` 模块，但当前脚本没有把预测、盘口、赛果和资金曲线串起来。
7. 可视化报告。项目底层有 `viz`，但当前 `full_predict.py` 只输出终端表格和可选 JSON。
8. GitHub Actions 定期重训。当前还没有 workflow 自动每天训练模型或生成报告。
9. 事件级 xT 分析。项目有 `xt` 模块，但需要事件级数据，当前脚本没有接入。
10. Opta 或 StatsBomb 的完整业务接入。README 和部分 MatchFlow helper 提到了专业数据源能力，但当前 `scrapers` 公共入口主要是 FootballData、Understat、ClubElo、FBRef。没有在当前预测脚本中接入商业 API 凭证和事件数据流水线。

## 16. 对当前项目能力的准确判断

当前项目已经具备比较完整的足球量化工具箱能力，尤其是数据抓取、进球建模、盘口概率、赔率隐含概率、评级、回测、投注工具、事件数据流、xT 和可视化基础设施。

当前 `full_predict.py` 已经可以作为比赛预测第一版入口使用，但它目前更像模型概率报告工具，不是完整投注建议系统。它的主要价值在于跑通了数据抓取、模型训练、模型保存、模型加载和单场预测流程。

要把它升级为你之前想要的赛前投注建议系统，最合理的路线是：先做定期重训和批量预测，再接入赔率和盘口 EV，随后做回测，最后再考虑 xG、Elo、伤停、阵容、赛程等信息的特征融合。

## 17. 建议的下一步开发顺序

第一步，加入 GitHub Actions 定期重训，让 `train` 命令每天自动运行，并把模型 bundle 和日志保存为 artifact。

第二步，新增比赛配置文件，例如 `configs/predictions/epl_matches.json`，让脚本读取多个待预测比赛，批量生成报告。

第三步，把 `betting.identify_value_bet`、`calculate_bet_value`、`kelly_criterion` 接入 `full_predict.py`，让赔率输入真正转化为 EV、edge、Kelly 仓位和价值投注判断。

第四步，接入回测模块，把历史预测、盘口、赛果和收益曲线串起来，评估每类模型和每类盘口的实际表现。

第五步，给报告加可视化输出，包括胜平负概率图、大小球概率图、亚洲让球概率图、精确比分热力图和长期回测收益曲线。

第六步，再设计 xG、Elo 和市场赔率的融合层。这个融合层应该独立于原生 Poisson 和 Dixon Coles 模型，避免误以为这些原生模型已经支持任意特征输入。
