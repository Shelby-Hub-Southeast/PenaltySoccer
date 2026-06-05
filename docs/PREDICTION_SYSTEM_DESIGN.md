# PenaltySoccer 预测系统设计文档

本文档用于规划 PenaltySoccer 后续从实验脚本升级为完整赛前预测与投注分析系统的设计方案。当前仓库是 `penaltyblog` 的 fork，底层已经提供数据抓取、进球模型、盘口概率、赔率隐含概率、投注价值计算、回测、评级、指标、可视化、事件数据流和 xT 等能力。我们新增的 `experiments/full_predict.py` 已经跑通了第一版单场预测流程，但它还不是完整系统。

## 1. 关键设计判断

### 1.1 不应该把所有功能都继续堆进 full_predict.py

`full_predict.py` 当前适合作为验证入口。它已经承担了数据抓取、模型训练、模型保存、模型加载、单场预测、Understat 上下文、ClubElo 上下文、终端报告输出等职责。如果继续把赔率 EV、Kelly、批量预测、回测、指标评估、可视化、GitHub Actions 适配、xG/Elo 融合、FBRef 增强都写进同一个文件，这个脚本会快速变成难以维护的巨型脚本。

更合理的方案是保留 `full_predict.py` 作为短期可运行入口，同时逐步抽象出应用层模块。应用层负责把 penaltyblog 的底层工具组合成我们的比赛预测系统。这样既能继续复用原项目能力，又不会把业务逻辑散落在一个实验脚本里。

### 1.2 不需要重新新建一个完全独立项目

当前阶段不建议再新建一个新仓库。原因是我们已经 fork 了 penaltyblog，并且需要直接改造和组合它的底层能力。新开项目会增加依赖同步、源码调试和版本管理成本。

推荐做法是在当前 fork 内增加一个应用层目录，例如：

```text
penaltysoccer/
  cli/
  data/
  models/
  prediction/
  betting/
  backtesting/
  reporting/
  visualization/
  config/
```

其中 `penaltyblog/` 尽量保持原项目核心库语义，`penaltysoccer/` 放我们的业务流程。短期内可以继续使用 `experiments/full_predict.py`，中期把它改成调用 `penaltysoccer` 包的薄入口。

### 1.3 full_predict.py 的最终定位

`full_predict.py` 最终不应该是核心业务代码，而应该成为示例脚本或调试脚本。正式入口可以逐步变成：

```bash
python -m penaltysoccer.cli predict --config configs/predictions/epl_matches.json
python -m penaltysoccer.cli train --config configs/training/epl.json
python -m penaltysoccer.cli backtest --config configs/backtest/epl_ou_ah.json
```

也可以后续在 `pyproject.toml` 中注册命令行入口，例如：

```bash
penaltysoccer train
penaltysoccer predict
penaltysoccer backtest
penaltysoccer report
```

## 2. 当前基础能力

当前 `full_predict.py` 已经完成的能力包括：

| 能力 | 当前状态 | 说明 |
| --- | --- | --- |
| FootballData 抓取 | 已接入 | 用于训练历史赛果模型 |
| Understat 抓取 | 已接入 | 当前只展示近期 xG 上下文 |
| ClubElo 抓取 | 已接入 | 当前只展示 Elo 差距 |
| 多模型训练 | 已接入 | 默认 Dixon Coles、Poisson、Bivariate Poisson |
| 可选模型池 | 部分接入 | 预留 Negative Binomial、Zero Inflated、Weibull Copula |
| 模型保存 | 已接入 | 以 pickle bundle 保存 |
| 模型加载 | 已接入 | 支持加载 bundle 后预测 |
| 胜平负概率 | 已接入 | 来自比分概率矩阵 |
| 大小球概率 | 已接入 | 支持整数、半球、四分之一球 |
| 亚洲让球概率 | 已接入 | 已改回 penaltyblog 标准符号 |
| 精确比分 | 已接入 | 输出高概率比分 |
| 1X2 市场赔率对比 | 初步接入 | 支持 `--odds-1x2`，只做隐含概率对比 |
| JSON 报告 | 已接入 | 支持 `--report-out` |

当前没有完整接入的能力包括投注 EV、Kelly、value bet、批量预测、回测、模型评估指标、可视化、定期重训、内部评级融合、FBRef 增强、事件数据和 xT。

## 3. 目标系统形态

目标不是只输出一场比赛的概率，而是形成一个完整工作流：

```text
数据抓取
  ↓
特征与上下文整理
  ↓
模型训练与保存
  ↓
批量比赛预测
  ↓
赔率与盘口价值计算
  ↓
报告输出
  ↓
回测评估
  ↓
定期自动运行
```

这个系统要回答三类问题。

第一，模型怎么看这场比赛。包括胜平负、期望进球、大小球、亚洲让球、精确比分、双方进球等概率。

第二，市场价格值不值得买。包括博彩公司赔率隐含概率、模型概率、edge、EV、Kelly 建议仓位、是否满足下注阈值。

第三，长期效果如何。包括回测命中率、ROI、最大回撤、Brier Score、RPS、不同盘口类型表现、不同模型表现。

## 4. 推荐目录结构

建议逐步新增如下结构：

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

`penaltysoccer` 是业务应用层，`penaltyblog` 继续作为底层量化库。这样后续如果要同步上游 penaltyblog，也更清晰。

## 5. 模块职责设计

### 5.1 data 模块

`data` 模块负责统一数据获取和清洗。短期内主要封装 FootballData、Understat、ClubElo、FBRef。

计划能力：

| 文件 | 职责 |
| --- | --- |
| `loaders.py` | 封装 FootballData、Understat、ClubElo、FBRef 调用 |
| `team_names.py` | 处理不同数据源球队名称不一致问题 |
| `fixtures.py` | 标准化赛程和赛果字段 |
| `markets.py` | 标准化赔率和盘口输入 |

重要设计点：球队名称必须统一。FootballData、Understat、ClubElo、FBRef 可能使用不同队名，例如 Man United、Manchester United、Man Utd。必须设计统一映射，否则多数据源融合会出错。

### 5.2 models 模块

`models` 模块负责模型注册、训练、保存、加载和集成。

计划能力：

| 文件 | 职责 |
| --- | --- |
| `registry.py` | 管理可用模型名称和类 |
| `training.py` | 根据配置训练模型 |
| `persistence.py` | 保存和加载模型 bundle |
| `ensemble.py` | 模型集成，包括简单平均、加权平均、基于回测表现加权 |

当前 `full_predict.py` 里 `MODEL_REGISTRY`、`train_models()`、`save_bundle()`、`load_bundle()` 都应该逐步迁移到这里。

### 5.3 prediction 模块

`prediction` 模块负责把训练好的模型应用到一场或多场比赛上。

计划能力：

| 文件 | 职责 |
| --- | --- |
| `single.py` | 单场预测 |
| `batch.py` | 批量预测 |
| `report_schema.py` | 定义预测报告结构 |

单场预测输出应包括：

```text
fixture 信息
模型列表
胜平负概率
期望进球
大小球概率
亚洲让球概率
双方进球概率
双重机会
精确比分
上下文信息
市场对比
投注价值分析
```

批量预测读取配置文件，例如：

```json
{
  "competition": "ENG Premier League",
  "season": "2025-2026",
  "model": "artifacts/models/epl_2025_2026_bundle.pkl",
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

### 5.4 betting 模块

`betting` 模块负责把模型概率转化为投注价值判断。它应该调用 `penaltyblog.betting` 的底层工具，而不是重复实现。

计划能力：

| 文件 | 职责 |
| --- | --- |
| `market_mapping.py` | 把预测概率映射到具体盘口市场 |
| `ev.py` | 计算 EV、edge、value bet |
| `kelly.py` | 计算 Kelly 或 fractional Kelly 仓位 |

核心公式：

```text
implied_probability = 1 / odds
edge = model_probability - implied_probability
EV = model_probability * (odds - 1) - (1 - model_probability)
```

要注意亚洲让球和整数大小球有 push。对于有 push 的盘口，EV 不能简单用 win/lose 二元公式，应该使用：

```text
EV = P(win) * (odds - 1) + P(push) * 0 - P(lose) * 1
```

四分之一盘口需要处理半赢、半输、半走，当前 `FootballProbabilityGrid` 已经给出 win、push、lose 概率，但业务层还要确保 EV 解释和盘口结算一致。

### 5.5 backtesting 模块

`backtesting` 模块负责把预测逻辑放回历史数据中检验。

计划能力：

| 文件 | 职责 |
| --- | --- |
| `strategies.py` | 定义策略，例如只买 EV 大于阈值的大小球 |
| `runner.py` | 调用 penaltyblog.backtest.Backtest 执行回测 |
| `results.py` | 输出命中率、ROI、资金曲线、按盘口分组统计 |

回测应至少支持：

```text
胜平负 value bet 回测
大小球 value bet 回测
亚洲让球 value bet 回测
不同模型单独回测
集成模型回测
不同 EV 阈值回测
不同 Kelly fraction 回测
```

这一步是判断项目是否真的有效的关键。没有回测，任何单场预测都只能作为参考。

### 5.6 metrics 模块

`metrics` 模块负责概率质量评估。底层可以直接使用 `penaltyblog.metrics`。

应输出：

```text
Brier Score
Ignorance Score
Ranked Probability Score
ROI
命中率
平均 EV
实际收益和预测 EV 的偏差
```

概率模型不应该只看命中率。长期看，模型给出的概率是否校准，比单场猜中更重要。

### 5.7 ratings 模块

`ratings` 模块负责把内部评级系统接入预测。

可接入：

```text
penaltyblog.ratings.Elo
penaltyblog.ratings.Massey
penaltyblog.ratings.Colley
penaltyblog.ratings.PiRatingSystem
```

短期目标不是直接替代进球模型，而是输出一套独立的评级概率，然后与进球模型概率做融合。

示例：

```text
最终主胜概率 = 0.75 * 进球模型主胜概率 + 0.25 * 评级模型主胜概率
```

权重不能拍脑袋长期固定，后面应该通过回测自动选择。

### 5.8 visualization 模块

`visualization` 模块负责生成图形报告。

优先图表：

```text
胜平负概率柱状图
大小球盘口概率曲线
亚洲让球赢盘概率曲线
精确比分热力图
模型间概率对比图
回测资金曲线
ROI 和命中率分组图
```

不建议第一阶段先做球场事件图。球场图和 xT 更依赖事件级数据，应该放在后期。

## 6. full_predict.py 的改造路线

当前 `full_predict.py` 应逐步从大脚本变成薄封装。建议分三阶段。

### 阶段 A：保留现状，新增功能仍可先写入 full_predict.py

短期为了快速验证，可以继续在 `full_predict.py` 中加小功能，例如：

```text
输入 totals 赔率并计算 EV
输入 asian handicap 赔率并计算 EV
保存更完整 JSON 报告
```

但新增代码应该尽量写成独立函数，为后续迁移做准备。

### 阶段 B：抽出核心模块

当 EV、批量预测和配置文件功能开始变多时，应该把以下内容迁移出去：

```text
模型注册和训练 → penaltysoccer.models
数据抓取 → penaltysoccer.data
单场预测 → penaltysoccer.prediction
投注价值计算 → penaltysoccer.betting
报告输出 → penaltysoccer.reporting
```

迁移后 `full_predict.py` 只负责解析命令行参数和调用模块。

### 阶段 C：正式 CLI

最终新增 `penaltysoccer.cli`，将 `full_predict.py` 降级为示例脚本。正式命令由 CLI 统一管理。

## 7. 功能迭代优先级

### P0：赔率 EV 和 Kelly

这是最贴近投注建议目标的能力。当前脚本只输出概率，没有判断赔率是否值得买。

新增能力：

```text
--odds-1x2 已有，增强为 EV 输出
--total-market line side odds
--ah-market side line odds
输出 EV、edge、Kelly、是否 value bet
```

示例命令：

```bash
python experiments/full_predict.py predict \
  --model artifacts/models/epl_2025_2026_bundle.pkl \
  --home "Arsenal" \
  --away "Chelsea" \
  --total-market 2.75 under 1.86 \
  --ah-market home -1.0 1.92
```

### P1：批量预测和配置文件

单场命令不适合实战。需要支持 JSON 配置。

新增能力：

```text
predict-batch
读取 configs/predictions/*.json
输出批量 JSON
输出终端摘要
```

### P2：GitHub Actions 定期重训

新增 workflow：

```text
.github/workflows/scheduled_predictions.yml
```

每天自动执行：

```text
pip install -e .
python experiments/full_predict.py train ...
python experiments/full_predict.py predict-batch ...
上传 artifacts/models 和 artifacts/reports
```

### P3：回测和指标

接入 `penaltyblog.backtest` 和 `penaltyblog.metrics`。

目标是回答：

```text
大小球策略长期 ROI 是否为正
让球策略长期 ROI 是否为正
哪个模型在英超更稳定
哪些盘口线最容易误判
EV 阈值设置多少更合理
```

### P4：内部评级融合

接入内部 Elo、Massey、Colley、PiRatingSystem。先输出评级概率，再做简单融合，最后通过回测确定权重。

### P5：可视化报告

生成 PNG 或 HTML 报告。先做概率图和回测图，不急着做事件球场图。

### P6：FBRef、xG、Elo 和市场融合增强

把 Understat xG、ClubElo、FBRef 球队统计、市场隐含概率真正转化为融合层输入。

注意，这不等于改造原生 Poisson 模型。更合理的是在进球模型输出之后做概率校准或加权融合。

### P7：事件数据和 xT

只有在获得稳定事件级数据后，再接入 MatchFlow 和 XTModel。没有事件数据时，这一步优先级低。

## 8. 赔率和盘口接入设计

### 8.1 1X2 市场

输入：

```json
{"home": 1.80, "draw": 3.80, "away": 4.50}
```

模型概率：

```text
P(home), P(draw), P(away)
```

输出：

```text
市场隐含概率
模型概率
edge
EV
Kelly fraction
是否 value bet
```

### 8.2 大小球市场

输入：

```json
{"line": 2.75, "over": 2.05, "under": 1.82}
```

模型概率来自：

```python
pred.totals(2.75)
```

输出应分别计算 Over 和 Under 的 EV。

需要注意 push 和四分之一盘结算。不能只比较 Over 概率和 `1 / odds`。

### 8.3 亚洲让球市场

输入：

```json
{"side": "home", "line": -1.0, "odds": 1.92}
```

模型概率来自：

```python
pred.asian_handicap_probs("home", -1.0)
```

输出：

```text
win probability
push probability
lose probability
EV
Kelly fraction
是否 value bet
```

当前系统统一采用 penaltyblog 标准：`home -0.5` 表示主队让 0.5，`home +0.5` 表示主队受让 0.5。

## 9. 回测设计

回测必须避免未来数据泄漏。每个比赛日只允许使用该比赛日前的数据训练模型。

基本流程：

```text
读取历史赛果和历史赔率
按日期排序
对每个比赛日：
  使用 date 之前的数据训练模型
  对 date 当天比赛生成概率
  根据赔率计算 EV
  满足策略条件则下注
  根据真实赛果结算
汇总 ROI、命中率、资金曲线和概率指标
```

策略示例：

```text
只买 EV > 0.03 的大小球
只买 Kelly fraction 在 0.01 到 0.05 之间的盘口
跳过模型分歧过大的比赛
跳过 odds 太低的市场
```

## 10. 数据泄漏和真实赛前预测

当前 `full_predict.py` 还没有 `cutoff-date`。如果用完整赛季 380 场训练，再预测同赛季的一场已赛比赛，就会有数据泄漏。

短期可以接受它作为功能测试。进入回测和赛前预测阶段后，必须做到：

```text
训练数据只包含比赛开始前已结束比赛
Understat 近期 xG 只包含比赛开始前数据
ClubElo 使用比赛日前日期
赔率使用赛前可获得赔率
禁止使用赛后统计作为预测输入
```

## 11. 配置文件设计

训练配置示例：

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

批量预测配置示例：

```json
{
  "model": "artifacts/models/epl_2025_2026_bundle.pkl",
  "report_out": "artifacts/reports/epl_predictions.json",
  "fixtures": [
    {
      "home": "Arsenal",
      "away": "Chelsea",
      "markets": {
        "1x2": {"home": 1.80, "draw": 3.80, "away": 4.50},
        "totals": [
          {"line": 2.5, "over": 1.91, "under": 1.95}
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

## 12. GitHub Actions 设计

建议新增一个手动触发和定时触发都支持的 workflow。

触发方式：

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "0 2 * * *"
```

基本步骤：

```text
checkout
setup python
pip install -e .
python experiments/full_predict.py train ...
python experiments/full_predict.py predict-batch ...
upload-artifact models
upload-artifact reports
upload-artifact logs
```

是否把模型提交回仓库，需要谨慎。模型是二进制文件，建议先作为 artifact 保存，不直接 commit 到仓库。

## 13. 风险和限制

1. FootballData 字段稳定，但赛季是否完整取决于数据源更新。
2. Understat 和 FBRef 是外部网页或接口，可能因为访问限制、页面变化、网络问题失败。
3. ClubElo 队名可能和 FootballData 不一致，需要 team mapping。
4. 当前进球模型不直接接收 xG、Elo、赔率作为训练特征。
5. 赔率 EV 必须正确处理 push 和四分之一盘，否则结论会失真。
6. 回测必须严格避免未来数据泄漏。
7. 只看单场结果无法评估模型质量，必须长期回测。
8. Bayesian 和事件级 xT 功能成本较高，不适合一开始进入每日自动任务。

## 14. 推荐下一步

下一步不要再继续扩大 `full_predict.py` 的展示内容，而是先接入投注价值计算。

建议第一个开发任务：

```text
在 full_predict.py 中新增 1X2、大小球、亚洲让球的 EV 和 Kelly 输出
```

这一步完成后，脚本才真正从概率报告工具变成投注分析工具。

第二个开发任务：

```text
新增批量预测配置文件和 predict-batch 命令
```

第三个开发任务：

```text
新增 GitHub Actions 定期重训和批量预测 workflow
```

第四个开发任务：

```text
新增回测脚本，验证大小球和亚洲让球策略
```

完成这四步后，再考虑 xG、Elo、FBRef 和可视化增强，会更稳妥。
