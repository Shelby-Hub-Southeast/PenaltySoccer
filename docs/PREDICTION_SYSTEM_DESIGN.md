# PenaltySoccer 应用层预测系统设计文档

本文档用于指导 PenaltySoccer 从 `penaltyblog` fork 直接发展为完整的赛前预测与投注分析应用。当前仓库底层已经具备数据抓取、进球模型、盘口概率、赔率隐含概率、投注价值计算、回测、评级、指标、可视化、事件数据流和 xT 等能力。后续开发将不再把 `experiments/full_predict.py` 作为主线，而是直接建设 `penaltysoccer/` 应用层。

## 1. 设计结论

### 1.1 放弃继续扩展 full_predict.py

`experiments/full_predict.py` 已经验证了基本链路：抓 FootballData 赛果、训练进球模型、保存模型、加载模型、预测单场比赛、输出胜平负、大小球、亚洲让球、Understat 近期 xG 和 ClubElo 上下文。它的价值是证明这条路可行。

从现在开始，`full_predict.py` 不再作为核心开发对象。后续功能不会继续堆到这个脚本里。它可以暂时保留在 `experiments/` 目录中，作为历史实验脚本和调试参考。等应用层稳定后，可以删除或改成很薄的示例脚本。

### 1.2 直接建设 penaltysoccer 应用层

正式业务逻辑放入新的 `penaltysoccer/` 包。`penaltyblog/` 继续作为底层量化工具库，尽量保持原项目语义。`penaltysoccer/` 负责把底层能力组合成我们的赛前预测、投注价值判断、回测、报告和自动化流程。

这样的分层更适合长期维护。底层库负责模型、数据源和通用工具；应用层负责业务流程、配置文件、批量任务、投注市场解释和报告输出。

### 1.3 当前仓库继续使用，不另开新项目

当前 fork 已经包含 penaltyblog 源码，并且我们需要深入复用和组合这些能力，所以继续在 `Shelby-Hub-Southeast/PenaltySoccer` 中开发。新建独立仓库会增加依赖同步、源码调试和版本管理成本。

## 2. 目标系统形态

目标系统要从单场概率输出升级为一套完整流程：

```text
配置文件
  ↓
数据抓取和标准化
  ↓
模型训练和模型保存
  ↓
单场或批量预测
  ↓
赔率、盘口、EV、Kelly 分析
  ↓
终端、JSON、Markdown、图像报告
  ↓
历史回测和指标评估
  ↓
GitHub Actions 定期运行
```

系统最终要回答三个问题。第一，模型如何看待比赛，包括胜平负、期望进球、大小球、亚洲让球、精确比分和双方进球。第二，当前赔率是否有价值，包括隐含概率、edge、EV、Kelly 仓位和是否满足下注阈值。第三，策略长期表现如何，包括 ROI、命中率、最大回撤、Brier Score、RPS 和分盘口统计。

## 3. 推荐目录结构

应用层按下面的结构创建：

```text
penaltysoccer/
  __init__.py

  cli/
    __init__.py
    main.py

  data/
    __init__.py
    loaders.py
    team_names.py
    fixtures.py
    markets.py

  models/
    __init__.py
    training.py
    registry.py
    ensemble.py
    persistence.py

  prediction/
    __init__.py
    single.py
    batch.py
    report_schema.py

  betting/
    __init__.py
    ev.py
    kelly.py
    market_mapping.py

  backtesting/
    __init__.py
    strategies.py
    runner.py
    results.py

  ratings/
    __init__.py
    rating_features.py

  reporting/
    __init__.py
    json_report.py
    markdown_report.py
    terminal_report.py

  visualization/
    __init__.py
    probability_charts.py
    score_heatmap.py
    backtest_charts.py

configs/
  training/
    epl.json
  predictions/
    epl_matches.json
  backtest/
    epl_value_bets.json

artifacts/
  models/
  reports/
  backtests/
  plots/
```

`artifacts/` 目录主要用于本地和 Actions 运行输出。模型文件、报告、回测结果和图片通常不建议直接提交到仓库，除非只是小型示例文件。

## 4. 模块职责

### 4.1 cli

`cli` 是正式命令入口。它负责解析命令行参数，读取配置文件，并调用其他模块。

第一版 CLI 设计：

```bash
python -m penaltysoccer.cli.main train --config configs/training/epl.json
python -m penaltysoccer.cli.main predict --config configs/predictions/epl_matches.json
python -m penaltysoccer.cli.main backtest --config configs/backtest/epl_value_bets.json
```

后续可以在 `pyproject.toml` 中注册命令：

```bash
penaltysoccer train --config configs/training/epl.json
penaltysoccer predict --config configs/predictions/epl_matches.json
penaltysoccer backtest --config configs/backtest/epl_value_bets.json
```

### 4.2 data

`data` 负责统一数据来源和字段格式。

`loaders.py` 封装 FootballData、Understat、ClubElo、FBRef 的调用。FootballData 作为第一阶段训练主数据源；Understat 用于 xG 和射门上下文；ClubElo 用于外部球队强弱评分；FBRef 作为可选增强源，主要用于球队和球员统计。

`team_names.py` 处理不同数据源之间的队名映射。这个模块非常重要，因为 FootballData、Understat、ClubElo、FBRef 的球队名称可能不一致。

`fixtures.py` 标准化赛程和赛果字段，例如 `date`、`kickoff`、`team_home`、`team_away`、`goals_home`、`goals_away`、`competition`、`season`。

`markets.py` 标准化赔率和盘口输入，包括 1X2、大小球和亚洲让球。系统统一采用 penaltyblog 标准盘口符号：选择 home 时，负数表示主队让球，正数表示主队受让。

### 4.3 models

`models` 负责模型注册、训练、保存、加载和集成。

`registry.py` 管理可用模型名称和类，例如 Dixon Coles、Poisson、Bivariate Poisson、Negative Binomial、Zero Inflated Poisson、Weibull Copula。Bayesian 和 Hierarchical Bayesian 可以作为高成本可选模型。

`training.py` 根据配置训练模型。第一阶段使用 FootballData 的历史赛果作为训练数据，输入为主客队、主客进球、时间权重和可选 neutral venue。

`persistence.py` 保存和加载模型 bundle。bundle 中应包含模型对象、训练元数据、训练数据摘要、数据源版本和警告信息。

`ensemble.py` 负责多模型集成。第一版使用简单平均。第二版加入基于回测表现的加权平均，例如用最近赛季的 RPS 或 Brier Score 反向加权。

### 4.4 prediction

`prediction` 负责单场和批量预测。

`single.py` 接收模型 bundle、主队、客队和市场信息，输出单场预测结果。

`batch.py` 读取配置文件中的多场比赛，循环调用单场预测，并汇总结果。

`report_schema.py` 定义预测报告结构，避免各模块传递松散字典。报告建议包含 fixture、model_probabilities、ensemble_probabilities、markets、betting_analysis、context、warnings、metadata。

### 4.5 betting

`betting` 负责把模型概率转成投注价值判断。它应调用 `penaltyblog.betting` 的底层工具，同时补充大小球和亚洲让球的 push 结算逻辑。

`market_mapping.py` 把模型输出映射到具体盘口。例如 2.5 大球对应 `pred.totals(2.5)` 的 over 概率，home -1.0 对应 `pred.asian_handicap_probs("home", -1.0)`。

`ev.py` 计算 edge 和 EV。对于没有 push 的市场可以使用二元公式：

```text
EV = P(win) * (odds - 1) - P(lose)
```

对于有 push 的市场必须使用：

```text
EV = P(win) * (odds - 1) + P(push) * 0 - P(lose)
```

四分之一盘口需要谨慎处理半赢、半输、半走。底层 `FootballProbabilityGrid` 已经能给出 win、push、lose 概率，但业务层仍要保证解释和真实结算规则一致。

`kelly.py` 计算 Kelly 或 fractional Kelly。实际使用时应默认 fractional Kelly，例如 0.25 Kelly 或 0.5 Kelly，避免仓位过大。

### 4.6 backtesting

`backtesting` 负责历史验证。它应优先复用 `penaltyblog.backtest.Backtest`、`Account` 和 `Context`。

`strategies.py` 定义策略，例如只买 EV 大于 3% 的大小球，只买 Kelly fraction 在 1% 到 5% 之间的盘口，或者跳过模型分歧过大的比赛。

`runner.py` 按日期推进回测。每个比赛日只允许使用该日期前的数据训练模型，避免未来数据泄漏。

`results.py` 生成结果摘要，包括投注数、命中数、命中率、利润、ROI、最大回撤、按盘口类型分组表现、按模型分组表现。

### 4.7 ratings

`ratings` 负责把内部评级系统接入预测流程。底层可使用 `penaltyblog.ratings.Elo`、`Massey`、`Colley`、`PiRatingSystem`。

第一阶段输出独立评级概率，作为报告中的辅助模型。第二阶段与进球模型概率融合。融合权重不能长期拍脑袋固定，后续应由回测决定。

### 4.8 reporting

`reporting` 负责报告输出。

`terminal_report.py` 输出终端表格，适合快速查看。

`json_report.py` 保存机器可读 JSON，适合 GitHub Actions artifact 和后续回测读取。

`markdown_report.py` 生成可读性更强的 Markdown 报告，适合保存每日预测结果。

### 4.9 visualization

`visualization` 负责图形报告。

第一阶段图表包括胜平负概率柱状图、大小球盘口概率曲线、亚洲让球赢盘概率曲线、精确比分热力图。

第二阶段图表包括回测资金曲线、ROI 分组图、模型概率校准图和模型间对比图。

球场图和 xT 图依赖事件级数据，优先级放到后面。

## 5. 配置文件设计

### 5.1 训练配置

`configs/training/epl.json` 示例：

```json
{
  "competition": "ENG Premier League",
  "season": "2025-2026",
  "models": ["dc", "poisson", "bivariate"],
  "xi": 0.001,
  "use_understat": true,
  "use_clubelo": true,
  "model_out": "artifacts/models/epl_2025_2026_bundle.pkl"
}
```

### 5.2 批量预测配置

`configs/predictions/epl_matches.json` 示例：

```json
{
  "model": "artifacts/models/epl_2025_2026_bundle.pkl",
  "report_out": "artifacts/reports/epl_predictions.json",
  "fixtures": [
    {
      "home": "Arsenal",
      "away": "Chelsea",
      "kickoff": "2025-11-29T17:30:00Z",
      "markets": {
        "1x2": {"home": 1.80, "draw": 3.80, "away": 4.50},
        "totals": [
          {"line": 2.5, "over": 1.91, "under": 1.95},
          {"line": 2.75, "over": 2.05, "under": 1.82}
        ],
        "asian_handicap": [
          {"side": "home", "line": -0.5, "odds": 1.85},
          {"side": "away", "line": 0.5, "odds": 2.00}
        ]
      }
    }
  ]
}
```

### 5.3 回测配置

`configs/backtest/epl_value_bets.json` 示例：

```json
{
  "competition": "ENG Premier League",
  "season": "2024-2025",
  "start_date": "2024-08-01",
  "end_date": "2025-05-31",
  "initial_bankroll": 1000,
  "strategy": {
    "markets": ["totals", "asian_handicap"],
    "min_ev": 0.03,
    "kelly_fraction": 0.25,
    "max_stake_fraction": 0.03
  }
}
```

## 6. 开发优先级

### P0：应用层骨架

创建 `penaltysoccer/` 包和配置目录。先把 `full_predict.py` 中已经验证过的功能迁移到应用层，保证新入口能完成训练和单场预测。

验收标准：

```bash
python -m penaltysoccer.cli.main train --config configs/training/epl.json
python -m penaltysoccer.cli.main predict --config configs/predictions/epl_matches.json
```

### P1：投注 EV 和 Kelly

接入 1X2、大小球、亚洲让球的 EV、edge 和 Kelly 输出。这一步完成后，系统才真正具备投注分析能力。

验收标准：预测报告中每个输入盘口都有模型概率、赔率、隐含概率、EV、edge、Kelly 和是否 value bet。

### P2：批量预测

支持读取 `configs/predictions/epl_matches.json`，一次预测多场比赛并输出汇总报告。

验收标准：同一个配置文件中多场比赛可以一次性生成 JSON 和终端摘要。

### P3：GitHub Actions 定期重训和预测

新增 workflow，每天自动训练模型、执行批量预测，并上传 artifacts。

验收标准：GitHub Actions 可手动触发，也可定时触发；运行结束后能下载模型和报告。

### P4：回测和评估指标

接入 `penaltyblog.backtest` 和 `penaltyblog.metrics`，验证策略长期表现。

验收标准：回测报告输出 ROI、命中率、资金曲线、Brier Score、RPS、按市场分组表现。

### P5：评级融合

接入内部 Elo、Massey、Colley、PiRatingSystem，输出评级概率，并与进球模型做可回测的加权融合。

### P6：可视化

生成预测图和回测图，包括胜平负概率图、大小球曲线、亚洲让球曲线、比分热力图和资金曲线。

### P7：增强数据和 xT

在有稳定事件级数据后接入 MatchFlow 和 XTModel。FBRef 可作为可选增强数据源，不能作为核心流程强依赖。

## 7. 数据泄漏要求

任何真实赛前预测和回测都必须避免未来数据泄漏。

要求如下：

```text
训练数据只包含比赛开始前已结束的比赛
Understat 近期 xG 只包含比赛开始前数据
ClubElo 使用比赛日前日期
赔率使用赛前可获得赔率
回测每个比赛日只能使用当日之前的数据训练模型
禁止使用赛后统计作为赛前输入
```

当前可以先不实现 `cutoff-date`，但回测模块开发时必须把这一点作为核心要求。

## 8. 近期开发任务拆分

第一步，创建应用层目录和基础文件，提交空包结构、配置目录和 README 注释。

第二步，把 `full_predict.py` 中的数据加载、模型训练、模型保存、单场预测和终端报告迁移到 `penaltysoccer/`。

第三步，新增 `predict` 配置文件入口，让系统从 JSON 读取比赛，而不是靠命令行传一场比赛。

第四步，接入 EV 和 Kelly，优先支持 1X2、大小球和亚洲让球。

第五步，做批量预测和 JSON 报告。

第六步，新增 GitHub Actions。

第七步，开始回测模块。

## 9. 与 full_predict.py 的关系

从本次设计更新开始，`full_predict.py` 不再承担新增功能。它保留在 `experiments/` 目录中，仅作为早期实验记录。

新功能统一进入 `penaltysoccer/` 应用层。开发时可以参考 `full_predict.py` 已经跑通的实现，但不要继续扩展它。

当 `penaltysoccer.cli` 稳定后，可以执行一次清理：

```text
保留 experiments/full_predict.py 作为 deprecated 示例
或者删除 experiments/full_predict.py
或者改为调用 penaltysoccer.cli 的简单包装
```

## 10. 下一步

下一步直接创建应用层骨架，先实现 P0。

P0 的目标不是一次性实现所有高级能力，而是把项目从实验脚本正式转向可维护的应用结构。完成 P0 后，再进入 P1 的投注 EV 和 Kelly。