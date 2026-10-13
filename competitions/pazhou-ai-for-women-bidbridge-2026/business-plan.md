# BidBridge — Evidence-bound procurement copilot for women entrepreneurs

**Competition:** Fifth Pazhou Algorithm Competition — “Algorithms for Good, A Smart Future for Women” / AI for Women Product Special Competition  
**Lane:** Women-friendly AI product (女性友好AI产品)  
**Status of this document:** DRAFT submission material. Owner must review identity, legal, team, IP, and portal fields before submission.  
**Product status:** Working public-source prototype with synthetic demo data and deterministic tests. No customer, pilot, revenue, registration, submission, acceptance, or award is claimed.

---

## 0. 一页中文摘要 / Chinese one-page summary

### 项目名称

**BidBridge — 面向女性创业者与小微团队的循证招投标协作助手**

### 项目定位

BidBridge 聚焦女性创业赋能场景，帮助女性创业者、女性友好型企业及小型服务团队把复杂的招标/RFP材料转化为**可核验、可解释、可执行的机会评审清单**。产品不替用户宣称资质，不自动提交投标，也不把“大模型猜测”当成合规事实。

### 用户痛点

小型企业参加政府和大型企业采购时，常见困难不是“找不到机会”，而是：

1. 招标文件版本与截止时间复杂；
2. 强制要求散落在长文档和附件中；
3. 资质、项目经验、技术方案、价格表、证书等证据难以保持最新且与当前版本绑定；
4. 需要合作伙伴/分包商时，依赖关系不透明；
5. 创始人团队时间有限，容易在不满足关键条件的机会中投入大量准备时间。

女性创业者是一个规模很大的商业群体。美国人口普查局公布的2023参考年度数据显示，美国共有约1,420万家女性拥有的雇主及非雇主企业，合计收入约2.8万亿美元。美国小企业管理局（SBA）同时设有女性拥有小企业（WOSB）联邦采购项目，联邦政府女性拥有小企业采购目标为5%。这些事实证明，女性创业与采购市场都是真实存在的大规模经济活动，而不是为了赛事临时创造的用户画像。

### 核心功能

BidBridge 将用户提供的招标事实、当前证据和团队资源转化为五种保守状态：

- `HOLD`：证据/版本/时间冲突，必须先解决事实问题；
- `NOT_OPEN`：机会尚未开放；
- `NO_BID_REVIEW_REQUIRED`：截止已过、存在不可补救强制缺口，或时间/容量不足；
- `READY_FOR_GAP_REVIEW`：仍有可补救缺口、合作依赖或部分材料；
- `READY_FOR_BID_DECISION`：所有强制要求已有证据，且准备时间/缓冲满足用户策略，等待负责人最终决定。

每个状态都附带确定性的关键路径队列：硬性缺口、外部合作依赖、部分材料、提问截止、提交缓冲与容量短缺分开呈现。

### 产品差异

多数“AI投标助手”重点生成文本。BidBridge 的核心不是多写一段方案，而是**让AI生成和企业事实之间存在可审计的边界**：

- 证据必须绑定当前机会版本；
- 缺失事实保持缺失，不用大模型补齐；
- “可投标”不等于“合规/有竞争力/会中标”；
- 合作伙伴候选信息不等于联系/承诺授权；
- 工具不自动登录采购平台、不提交、不签署合同。

### 商业化方向（假设，尚未验证）

第一阶段面向1–10人的专业服务、技术咨询、数据/软件服务和本地供应商团队，采用“免费单机会演示 + 付费工作区”的SaaS模式。定价、获客成本、转化率与留存率均需通过真实用户实验验证，本方案不把这些假设写成既有收入。

### 当前可验证成果

- 静态网页演示，可在浏览器中运行；
- checked-in synthetic RFP 示例，不包含真实客户数据；
- JavaScript 决策核心，可在浏览器和 Node.js 运行；
- 20个确定性测试覆盖截止时间、证据新鲜度、版本冲突、强制缺口、合作依赖、容量边界、敏感引用和DOM安全；
- 所有外部动作权限默认 `false`。

---

## 1. Executive summary

BidBridge is an evidence-bound procurement/RFP copilot designed for women entrepreneurs and other small owner-led teams that want to compete for structured purchasing opportunities without turning AI output into unsupported compliance claims.

The product addresses the operating layer between **finding an opportunity** and **writing/submitting a proposal**. It converts operator-supplied solicitation facts, mandatory requirements, current evidence, partner dependencies, deadlines, and preparation capacity into a deterministic owner review state and critical-path queue.

The key design choice is restraint: BidBridge does not infer that a company is certified, eligible, compliant, competitive, profitable, or likely to win. It does not contact an issuer or partner, register a vendor, mutate a procurement portal, submit a question, submit a bid, make a teaming commitment, sign a contract, move money, or make the owner’s go/no-go decision.

This positioning is directly relevant to the Pazhou women-friendly product lane, which explicitly welcomes products addressing women’s workplace empowerment and entrepreneurship. The product is **women-friendly, not women-exclusive**: the initial market design emphasizes women entrepreneurs because the competition asks for real female-user value, while the underlying workflow can serve any small business that needs evidence-disciplined proposal operations.

## 2. Why this is a women-friendly AI product

### 2.1 A real economic user base

The latest U.S. Census Bureau release available during preparation reported **14.2 million women-owned U.S. employer and nonemployer businesses in 2023**, with **$2.8 trillion in receipts**. The same release reported 1.4 million women-owned employer firms and 12.9 million women-owned nonemployer businesses.

Source: U.S. Census Bureau, “Census Bureau Releases New Data About Characteristics of Employer and Nonemployer Business Owners,” published Nov. 20, 2025:  
https://www.census.gov/newsroom/press-releases/2025/business-owner-characteristics.html

This is not evidence that every woman entrepreneur wants procurement software. It is evidence that the target segment is economically material enough to test a focused product thesis.

### 2.2 Procurement has explicit women-owned-business channels

The U.S. Small Business Administration states that the federal government’s contracting goal includes **5% of contracting dollars for women-owned small businesses**, and it operates the Women-Owned Small Business (WOSB) Federal Contract program.

Sources:  
https://www.sba.gov/certifications/  
https://www.sba.gov/contracting-officials/

SBA also reports historical FY2022 prime contracting of more than $28.1 billion to women-owned small businesses, approximately 4.57% of overall contracting dollars at that time. We treat that figure as historical context, not as a current-year market-size claim.

### 2.3 Small-team operating constraints matter

The Census Bureau has separately reported that women-owned employer businesses were consistently more likely than male-owned employer businesses to have a sole owner in its 2018–2021 analysis.

Source:  
https://www.census.gov/library/stories/2024/11/single-owner-businesses.html

That observation does **not** prove a causal disadvantage or a specific procurement burden. It does support a testable product hypothesis: a meaningful subset of women-owned firms may have limited dedicated proposal-operations staff, making structured evidence and deadline tools valuable.

### 2.4 User-value thesis

BidBridge is therefore designed around a concrete value promise:

> Help an owner-led business spend scarce proposal time on opportunities whose mandatory requirements, evidence, dependencies, and deadlines are visible — and fail closed when those facts are not proven.

We will validate whether women entrepreneurs value this workflow through user interviews and product telemetry rather than assuming gender alone predicts product behavior.

## 3. The problem

Procurement opportunities arrive as web pages, PDFs, amendments, spreadsheets, forms, and portal fields. A small supplier must often answer five different questions before proposal writing even begins:

1. **What version of the opportunity are we evaluating?**
2. **What is mandatory versus desirable?**
3. **What current evidence proves each mandatory requirement?**
4. **What depends on a partner, certification, or external document?**
5. **Can this team finish the remaining work while preserving a safe submission buffer?**

Generic AI assistants can summarize or draft text, but a fluent answer can hide uncertainty. A procurement copilot needs a stronger boundary: unknown evidence remains unknown; old evidence remains old; a new amendment invalidates old requirement mappings until rechecked.

## 4. Product workflow

### Step 1 — Capture the opportunity snapshot

An opportunity record contains:

- stable opportunity ID;
- source revision;
- source digest and bounded source reference;
- capture/open/questions/submission timestamps;
- submission mode;
- optional source reference amount in exact minor currency units;
- mandatory requirement rows.

A production connector could create this from a procurement portal or document parser. The current prototype uses checked-in synthetic data only.

### Step 2 — Build the mandatory requirement matrix

Each requirement is classified into a bounded type such as:

- eligibility;
- technical;
- experience;
- price;
- form;
- certification;
- teaming;
- other structured requirement.

Each row also records whether evidence is required, whether teaming is allowed, its deadline, and an owner-supplied effort reference.

### Step 3 — Bind current evidence

Every mandatory requirement must have exactly one current evidence state:

- `SATISFIED`;
- `PARTIAL`;
- `MISSING`;
- `NOT_APPLICABLE_CONFIRMED`;
- `NEEDS_EXTERNAL_PARTNER`.

Evidence includes an immutable event ID, opportunity revision, observation timestamp, digest, and bounded reference. Explicit N/A requires a separate authority digest.

### Step 4 — Model partner dependencies without contacting anyone

A team candidate can be associated with a teamable requirement and an internal state such as:

- identified;
- contact pending;
- evidence pending;
- ready for review.

The current product never treats a candidate record as permission to contact or commit that partner.

### Step 5 — Apply owner capacity and deadline policy

The user supplies:

- preparation hours available;
- reserve hours that must remain untouched;
- minimum submission buffer;
- maximum evidence age;
- question-deadline warning window.

The engine uses a caller-supplied trusted review time (`asOf`) and exact integer arithmetic. Candidate input cannot silently set the trusted clock.

### Step 6 — Produce an explainable review state

The product returns one conservative state plus a sorted queue. A state is a **review state**, not a legal or procurement conclusion.

## 5. Current working prototype

### 5.1 Static browser demo

The current carrier contains a dependency-free browser interface. It loads a checked-in fictional opportunity and shows:

- owner review state;
- time to submission;
- remaining effort;
- usable preparation capacity;
- requirement/evidence matrix;
- critical-path queue;
- all-false external authority map.

Candidate strings are rendered with DOM `textContent`; the demo does not insert candidate text using `innerHTML`.

### 5.2 Deterministic JavaScript engine

The engine runs in modern browsers and Node.js and validates:

- exact object shape;
- bounded IDs and refs;
- SHA-256-shaped evidence/source digests;
- canonical UTC timestamps;
- safe integers and boolean-vs-integer aliases;
- source amount/currency consistency;
- chronology;
- complete mandatory evidence coverage;
- current opportunity revision binding;
- evidence/team freshness;
- explicit N/A authority;
- teaming only where allowed;
- capacity and submission-buffer arithmetic.

### 5.3 Hostile tests

At preparation time the focused suite contains 20 tests covering:

- synthetic demo happy path;
- all-ready state;
- pre-open state;
- exact submission deadline boundary;
- non-teamable hard blocker;
- teamable missing gap;
- explicit N/A authority;
- incomplete/conflicting evidence;
- changed bytes under one event ID;
- future/stale/prior-revision evidence;
- question warning;
- exact capacity threshold;
- partner/contact authority separation;
- prohibited teaming placement;
- input-order invariance;
- PII/secret-shaped ref rejection;
- unsafe integer/bool alias rejection;
- canonical timestamp enforcement;
- truth-preserving presentation helpers;
- browser DOM-safety guard.

The checked-in workflow reruns the same suite on pull request and main changes scoped to this competition path.

## 6. Technical architecture

### Current architecture

```text
synthetic opportunity JSON
        |
        v
strict structural validation
        |
        +--> requirement matrix
        +--> evidence currentness/revision checks
        +--> teaming dependency checks
        +--> owner capacity/deadline arithmetic
        |
        v
deterministic review state + critical-path queue
        |
        v
static browser UI (textContent-only candidate rendering)
```

### Production architecture hypothesis

```text
source connectors
  procurement portal / email / PDF / spreadsheet
        |
        v
versioned source vault + extraction layer
        |
        v
human-confirmed requirement/evidence graph
        |
        v
BidBridge deterministic decision core
        |
        +--> owner dashboard
        +--> question calendar reminders
        +--> proposal workspace handoff
        +--> audit/export packet
```

The generative layer should propose extraction candidates and draft language; the deterministic layer should own evidence status, chronology, and authority boundaries.

## 7. AI design

The prototype decision core is deliberately deterministic rather than pretending every part of procurement needs a language model. Planned AI components include:

1. **Requirement extraction:** propose mandatory requirement rows from solicitation text with source-span citations.
2. **Amendment diffing:** identify requirement/deadline changes across revisions.
3. **Evidence matching:** propose links between requirements and the owner’s document/evidence library.
4. **Gap explanation:** translate structured blockers into concise owner-facing language.
5. **Draft assistance:** generate proposal skeletons only after requirement/evidence state is explicit.

The user must be able to inspect the source for every extracted requirement and accept/reject AI proposals. AI output never promotes itself to verified evidence.

## 8. Safety, trust, and governance

BidBridge’s all-false authority model is a product feature, not a disclaimer added after the fact.

The current engine grants no authority for:

- issuer contact;
- partner contact;
- vendor registration;
- portal mutation;
- question submission;
- bid submission;
- teaming commitments;
- signatures/contracts;
- eligibility/compliance representations;
- staffing/scheduling;
- bank/payment mutation;
- autonomous go/no-go decisions;
- award or revenue claims.

### Privacy design

The prototype rejects obvious PII/secret-shaped durable refs because the demo has no reason to store them. A production system would require encrypted storage, tenant isolation, access controls, retention rules, and explicit secret handling before ingesting real customer material.

### Human decision model

BidBridge is not a legal advisor or procurement officer. It should make the state of evidence legible enough that the owner can decide what to verify next.

## 9. Differentiation

### Against generic chatbots

Generic assistants optimize for helpful prose. BidBridge optimizes for **evidence discipline**:

- complete mandatory matrix;
- current revision binding;
- evidence freshness;
- no hidden truth promotion;
- deterministic deadline/capacity arithmetic;
- explicit external-action authority.

### Against document repositories

Document repositories can store certificates, past performance, and templates. BidBridge connects those artifacts to a specific solicitation revision and asks whether every mandatory row has current evidence.

### Against bid-writing software

Bid-writing software often begins once a team has decided to pursue. BidBridge focuses on the pre-bid evidence and capacity decision, and can hand a clean requirement graph to a writing workspace.

## 10. Initial target users

We propose three initial user archetypes, all requiring validation:

### A. Solo or micro professional-service firm

Examples: data analysis, software integration, research support, technical writing, design, training, operations consulting.

Need: quickly reject bad-fit opportunities and keep evidence for good-fit ones organized.

### B. Women-owned small business entering structured procurement

Need: translate eligibility/certification/past-performance/technical/form requirements into a current proof matrix without assuming certification status.

### C. Small prime assembling partner coverage

Need: make teamable gaps and missing partner evidence visible before commitments are made.

The product does not require a user to disclose gender to function. Gender-focused positioning is a go-to-market and product-research choice for this competition lane, not an access gate.

## 11. Commercial model — hypotheses to test

No pricing below is claimed as existing revenue.

### Free review

- one synthetic/demo opportunity;
- manual structured input;
- deterministic gap/deadline review;
- educational examples.

Goal: lower trust barrier and demonstrate that the product does not invent compliance.

### Solo workspace — hypothesis: USD 39–79/month

- 10 active opportunities;
- evidence library;
- revision diffing;
- owner reminders;
- exportable requirement matrix.

### Team workspace — hypothesis: USD 149–299/month

- multi-user review;
- controlled evidence assignments;
- partner dependency ledger;
- proposal handoff;
- change/audit history.

### Assisted setup — hypothesis: fixed onboarding package

- configure evidence taxonomy;
- import current certificates/past-performance references;
- define owner capacity/buffer policy;
- train the team on review states.

This is a setup service, not an eligibility certification or promise of award.

## 12. Go-to-market experiments

### Experiment 1 — problem interviews

Target: 20 owner-led firms that have responded to public or enterprise RFPs, with deliberate inclusion of women-owned firms.

Questions:

- What caused the last no-bid or late-bid decision?
- How are mandatory requirements tracked today?
- What evidence becomes stale most often?
- What partner dependency causes the most delay?
- Would the owner pay to reduce no-fit pursuit time, and how would they measure value?

Success criterion: at least 8/20 describe requirement/evidence/deadline coordination as a top-three workflow pain. This is a proposed threshold, not a current result.

### Experiment 2 — concierge prototype

Offer a no-auto-submit opportunity review using customer-supplied documents. Measure:

- setup time;
- requirements identified;
- owner corrections to extraction;
- hard blockers surfaced before proposal drafting;
- minutes saved versus existing spreadsheet workflow.

Real customer data would require a privacy/storage review before use in the current prototype.

### Experiment 3 — partner channel discovery

Potential future channels to interview, without implying endorsement or affiliation:

- Women’s Business Centers;
- APEX Accelerator procurement counselors;
- local economic-development organizations;
- bid/proposal consultants;
- chambers and supplier-diversity communities.

## 13. Product metrics

We will not optimize only for generated words or number of opportunities imported.

### Trust metrics

- mandatory requirement coverage rate;
- source-span acceptance rate;
- evidence mismatch rate;
- amendment drift detected before owner decision;
- false “ready” incidents (target: zero in deterministic core).

### User-value metrics

- minutes to initial opportunity triage;
- owner corrections per extracted requirement;
- no-bid decisions reached before proposal-writing spend;
- opportunities with complete evidence matrix before drafting;
- repeat weekly active use.

### Commercial metrics

- free-to-paid conversion;
- paid workspace retention;
- onboarding time;
- gross margin;
- support hours per account.

These are planned metrics, not current performance claims.

## 14. Guangzhou / China localization path

Winning or participating in Pazhou would be useful only if the product can adapt beyond a U.S.-specific certification story.

### Localization priorities

1. Bilingual Chinese/English opportunity and evidence labels.
2. Local procurement taxonomy and timestamp/time-zone handling.
3. Connectors for public tender notices and enterprise procurement documents, subject to site terms and lawful access.
4. Certificate/evidence templates that are configured per buyer/jurisdiction rather than hard-coded.
5. Cross-border supplier mode for companies responding to English and Chinese opportunities.
6. China-hosted deployment option only after data-residency, cybersecurity, privacy, licensing, and legal review.

### What is deliberately not claimed

- We have not integrated a Chinese procurement portal.
- We have not validated local legal/compliance requirements.
- We have no Guangzhou customer or partner claim.
- We have not localized data hosting.

The competition can accelerate those validation steps; it should not be used to pretend they are already complete.

## 15. Roadmap

### Phase 0 — current prototype

- deterministic decision core;
- synthetic demo;
- requirement/evidence/team/capacity model;
- browser UI;
- hostile tests;
- submission/business-plan packet.

### Phase 1 — 0–8 weeks after validation decision

- source-span model for PDF/text extraction;
- amendment diffing;
- encrypted local evidence workspace;
- manual evidence confirmation;
- exportable owner review report;
- 10–20 structured user interviews.

### Phase 2 — 2–5 months

- procurement feed connectors where permitted;
- organization evidence library;
- multi-user review;
- reminder/calendar export;
- proposal-writing handoff;
- initial paid pilots only after privacy/security controls are adequate.

### Phase 3 — 5–12 months

- bilingual workflow;
- partner ecosystem experiments;
- buyer/jurisdiction policy packs;
- API/agent integrations;
- enterprise audit and tenant-isolation hardening.

## 16. Defensibility

The moat is not “we call an LLM.” It is the structured evidence graph and operational feedback loop:

- opportunity revisions;
- source-bound mandatory requirements;
- organization-specific evidence history;
- requirement-to-evidence corrections;
- team dependency patterns;
- time/capacity policy;
- audit history of owner decisions.

Over time, this can improve extraction and prioritization while retaining a deterministic truth boundary.

## 17. Competition alignment

The official women-friendly track describes solutions for women’s workplace empowerment, health, safety, parenting, emotional wellbeing, entrepreneurship, aesthetics, and other real-life needs. BidBridge fits **women entrepreneurship empowerment**.

Official track page:  
https://www.aicompetition-pz.com/topic_detail/48

The official page states:

- women-friendly lane team size is at most 5;
- there is no female-member minimum for this lane;
- project application + project proposal are required;
- technical docs, demo video/screenshots, qualifications, innovation/result evidence may supplement;
- product registration cutoff is Sept. 15, 2026;
- lane awards are ¥50,000 / ¥30,000 / ¥20,000 for first/second/third, subject to official qualification/result/tax rules.

## 18. Important competition IP term

The current general participation guidelines state that submitted works are jointly owned by the contestant and the competition organizing committee, and that the organizer may publicly display submitted works while committing not to make profit-making transactions from them.

Official guidelines:  
https://www.aicompetition-pz.com/guidelines

**Owner action before submission:** review the portal’s final terms and decide exactly which code, screenshots, plan text, and other assets should be submitted under that ownership/display term. This preparation carrier does not accept those terms on the owner’s behalf.

## 19. Use of prize / support — proposed

If the project were awarded cash or incubation support, proposed use would be:

1. security/privacy engineering for real customer evidence;
2. bilingual document extraction and amendment diffing;
3. user research with women entrepreneurs and procurement counselors;
4. lawful portal/document connectors;
5. hosting and reliability;
6. limited travel/localization work if the owner separately approves it.

No prize is assumed or booked as revenue.

## 20. Team statement — owner must complete

Current technical prototype preparation is attributable to the repository owner and automated engineering collaborators recorded in the public development history.

Before submission, the owner must provide truthful portal-specific fields for:

- team leader legal name;
- nationality/residence as requested;
- organization/school or individual status;
- phone/email verification;
- team member roster;
- each member’s role;
- any company registration information;
- IP ownership/authorization declarations.

No placeholder should be submitted as fact.

## 21. Evidence ledger

| Claim | Status | Evidence |
|---|---|---|
| Pazhou women-friendly product lane is open in current site | VERIFIED during preparation | Official topic/registration pages |
| Women-friendly lane has no female-member minimum | VERIFIED | Official topic page |
| Deadline shown as Sept. 15, 2026 | VERIFIED | Official topic page |
| Awards shown as ¥50k / ¥30k / ¥20k | VERIFIED | Official topic page |
| Contest guidelines include joint ownership/display term | VERIFIED | Official guidelines |
| U.S. women-owned businesses = 14.2M / $2.8T receipts for 2023 reference year | VERIFIED | U.S. Census 2025 release |
| U.S. federal WOSB contracting goal = 5% | VERIFIED | SBA |
| BidBridge browser prototype exists | VERIFIED in repository carrier | `index.html`, `bidbridge.js` |
| Synthetic demo works deterministically | VERIFIED by focused tests | `test_bidbridge.mjs` |
| Real women entrepreneurs want/pay for this product | NOT YET VERIFIED | planned interviews |
| Proposed pricing | HYPOTHESIS | validation required |
| Guangzhou localization works today | NOT VERIFIED | roadmap item |
| Customer/pilot/revenue | NONE CLAIMED | n/a |
| Pazhou registration/submission/award | NONE CLAIMED | owner/portal action required |

## 22. Risks and mitigations

### Risk: AI extraction misses a mandatory requirement

Mitigation: require source-span evidence; show completeness uncertainty; keep final requirement acceptance with the user.

### Risk: stale certificate/past-performance evidence is treated as current

Mitigation: freshness policy + source/revision/timestamp binding; stale evidence routes to HOLD.

### Risk: user interprets READY as “compliant”

Mitigation: states are explicitly named owner-review states; authority map and UI language prohibit compliance/award interpretations.

### Risk: privacy exposure in proposal documents

Mitigation: current demo uses synthetic data only; production real-data ingestion is blocked on encryption, tenant isolation, retention, and access-control design.

### Risk: women-friendly positioning becomes superficial

Mitigation: test with women entrepreneurs; measure actual workflow pain and outcomes; do not use gender stereotypes as product logic; product function does not require gender disclosure.

### Risk: competition IP terms conflict with future commercialization strategy

Mitigation: owner reviews final portal terms and limits submitted assets accordingly; keep generic open prototype separate from private customer data/connectors.

## 23. What a judge can verify immediately

1. Open the static demo.
2. Observe the synthetic opportunity is visibly labeled synthetic.
3. Change the trusted review time and rerun.
4. See partial and partner-dependent requirements appear separately.
5. Inspect the all-false external authority map.
6. Read the JavaScript decision core.
7. Run the Node focused tests.
8. Verify the project makes no customer, revenue, submission, or award claim.

That is the core product principle: **trust after proof, and keep unknowns unknown.**
