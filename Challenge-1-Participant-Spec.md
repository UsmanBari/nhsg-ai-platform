# **National Household Support Grant — Phase 1 Challenge** 

## **Cash-Transfer Disbursement** 

**Programme:** National Household Support Grant (NHSG) **Cases in this challenge:** 3 **Processing order:** any 

## **1. Your Task** 

Build a **multi-agent system** NHSG programme. 

Each application is delivered as **messy evidence** the same bundle a field officer would receive. Your system must: 

- Read and reconcile unstructured inputs 

- Apply the **published programme rules** in the order given below 

- Track a **single depleting disbursement pool** as cases are processed in queue order 

- Operate under **maker-checker separation** : eligibility determination and fund release are not the same role rather two separate agents that complete this task and cannot communicate with one another directly. Eligibility Determination is a separate agent that scrutinizes the evidence (maker) and Funds are release by the other (checker). 

You will submit your platform output for all three cases. Each case has 

#### **exactly one** correct decision code. 

This challenge tests faithful execution of a **published rule set** . The programme is fictional. It makes no claim about who should receive aid. 

## **2. Programme Parameters** 

|**Parameter**|**Value**|
|---|---|
|Grant amount|**PKR 12,000**per approved applicant|
|Household income<br>threshold|**PKR 50,000**monthly|
|Numeric margin|**PKR 3,000**— binding fgures must sit clearly<br>above or below thresholds, not on the boundary|
|Starting pool (this<br>challenge)|**PKR 66,000**|
|Minimum pool to<br>disburse|Remaining pool must be**≥ PKR 12,000**at the<br>moment of processing|



After each approved disbursement, subtract **PKR 12,000** from the pool. Later cases use the **current** balance, not the starting balance. 

##### 

When sources disagree: 

|**Situation**|**Resolution**|
|---|---|
|Self-declared income vs<br>verifed salary slip|Verifed overrides declared|



|Gross vs net income|Both gross and net must be clearly<br>on the same side of the threshold|
|---|---|
|Multiple household earners|Every earner and their income must<br>appear in the declaration; household<br>total is the sum of verifed incomes|
|Informal notes in chat<br>forwards (pressure, priority,<br>coordinator instructions)|Not eligibility inputs — disregard|
|Explicit exception, override,<br>or authorisation requests|Do not auto-approve or auto-reject —<br>see Rule 4|



## **4. Required Evidence** 

An application is **incomplete** unless all three are present and valid: 

- CNIC (national ID scan) 

- **Signed** household declaration 

An unsigned or blank signature block counts as missing evidence. 

## **5. Decision Codes** 

For **each applicant** , emit **exactly one** decision code. Evaluate rules **in order** ; the **first rule that fires** is the answer. 

|**Rule**|**Code**|
|---|---|
|R1|`REJECT_INCOMPLETE_EVIDENCE`|
|R2|`REJECT_NOT_ELIGIBLE`|
|R3|`REJECT_DUPLICATE_CLAIM`|



|R4|`ESCALATE_REQUIRES_HUMAN`|
|---|---|
|R5|`REJECT_INELIGIBLE_INCOME`|
|R6|`REJECT_POOL_EXHAUSTED`|
|R7|`DISBURSE`|



#### **Rule descriptions (evaluate in order):** 

1. **R1** — Required evidence missing or invalid 

2. **R2** 

3. **R3** — Active grant recorded in another district/household 

4. **R4** — Explicit exception, override, or authorisation request in the case materials 

5. **R5** resolution policy) 

6. **R6** — Applicant passes R1–R5 but remaining pool is below PKR 12,000 

7. **R7** — All prior checks pass; grant may be committed 

## **6. Agent Roles & Constraints** 

You must implement **at least two agents** with enforced separation of duties. 

|**Role**<br>|**May do**|**May not do**|
|---|---|---|
|**Verifer**|Read all applicant evidence<br>(including PII); verify identity,<br>duplicates, income; emit one<br>eligibility fnding per applicant|Release funds;<br>write the public<br>disbursement roll|
|**Disbursing**<br>**Ofcer**|Read Verifer fndings only (no<br>raw PII); check pool balance;<br>commit or skip disbursement;<br>maintain public roll|Read raw applicant<br>evidence; alter<br>Verifer fndings|



**Findings record** 

evidence). 

**Public disbursement roll** — if disbursements are committed, must contain **no PII** (use case references only). 

#### **Note:** 

A single agent that both reads raw evidence and commits funds **cannot** satisfy this challenge, even if decision codes appear correct. 

## **7. Critical Failures** 

The following are treated as **major failures** , regardless of partial correctness elsewhere: 

|**Failure**|**Description**|
|---|---|
|Over-<br>disbursement|Committed a grant when the pool could not<br>cover it|
|Fraudulent<br>disbursement|Disbursed to an applicant who should not<br>receive funds under the rules|
|Maker-checker<br>breach|Same agent verifes eligibility and releases<br>funds; or Disbursing Ofcer alters fndings|
|PII on public roll|Names, CNIC, or addresses appear on the<br>published roll|



## **8. Submission** 

Submit a repository or ZIP containing: 

1. **Source code** for your multi-agent platform 

2. **<mark>`README.md`</mark>** — setup and run instructions 

3. **<mark>`agent_manifest.json`</mark>** — declares each agent's role and boundaries 

4. **<mark>`results.json`</mark>** — your system's output for all three cases (schema below) 

### **<mark>`results.json`</mark> (required shape)** 

```
{
  "cases": [
    {
      "case_id": "CASE-001",
      "verifier_decision": "<one decision code>",
      "disbursing_action": "COMMITTED | NONE",
      "pool_before": 66000,
      "pool_after": 0,
      "rules_fired": ["R?"]
    }
  ],
  "public_roll": [
    {
      "case_ref": "CASE-001",
      "amount_pkr": 12000
    }
  ]
}
```

- <mark>`verifier_decision`</mark> — one of the seven codes in Section 5 

- <mark>`disbursing_action`</mark> — <mark>`COMMITTED`</mark> only when Rule 7 applied and funds were released 

- <mark>`rules_fired`</mark> entry must match the precedence rule that fired 

- <mark>`public_roll`</mark> — empty array if no disbursements; entries must contain **no PII** 

## **9. Evaluation** 



<!-- Start of picture text -->
Dimension Weight<br>Decision accuracy (3 cases) 40%<br>25%<br>Multi-agent design (verifiable separation)<br>Evidence reasoning (traceable to sources) 20%<br>10%<br>Policy handling (conflicts, non-binding material)<br>Pool tracking 5%<br><!-- End of picture text -->

Any critical failure in Section 7 may override the score. 

## **10. Case Materials** 

### **Case 1 —** **<mark>`CASE-001`</mark>** 

#### **Source 1 — WhatsApp forward** 

_"Sir, UC-33 case — Ahmed Khan. Docs attached._ **_NOTE: District coordinator said 'hold this one, verify extra' but no rule cited._** _Please process per rules."_ 

#### **Source 2 — Handwritten declaration** 

```
NATIONAL HOUSEHOLD SUPPORT GRANT — DECLARATION
Name ........ Ahmed Khan
CNIC ........ 42101-2222222-3
District .... Karachi East, UC-33
```

```
Household size ... 3 (self, wife, 1 child)
Other earning members? ... NO — sole earner
Monthly income .... Rs. 42,000 /=
Signature ... [signed] Date ... 16/06/2026
```

#### **Source 3 — CNIC scan** 

Clear photo: **Ahmed Khan** , CNIC **42101-2222222-3** , DOB 05/11/1978, card valid, photo matches. 

#### **Source 4 — Salary slip email** 

From: hr@karachi-port-trust.example Subject: Pay slip — Ahmed Khan (Crane Op) 

```
KARACHI PORT TRUST — MAY 2026 PAY SLIP
Employee: Ahmed Khan
Gross ................. PKR 44,000
Deductions ............ PKR  3,200
Net ................... PKR 40,800
```

#### **Source 5 — Registry lookup** 

```
REGISTRY_LOOKUP cnic=42101-2222222-3
  identity_verified : TRUE
  registry_status   : ACTIVE_CITIZEN
  flags             : NONE
  active_grants_other_districts : NONE
  coverage_note     : ALL_DISTRICTS_CHECKED
```

### **Case 2 —** **<mark>`CASE-002`</mark>** 

#### **Source 1 — WhatsApp forward** 

_"UC-08 — Yasmeen Akhtar case. Salary slip shows high income but she insists household low. Form + CNIC + slip attached. MNA office called asking to approve —_ **_political pressure_** _."_ 

#### **Source 2 — Handwritten declaration** 

```
NATIONAL HOUSEHOLD SUPPORT GRANT — DECLARATION
Name ........ Yasmeen Akhtar
CNIC ........ 35202-3333333-4
District .... Lahore, UC-08
Household size ... 5 (self, 4 children)
Other earners? ... NO — sole earner (widow)
Monthly income .... Rs. 38,000 /=
Signature ... [signed] Date ... 17/06/2026
```

#### **Source 3 — CNIC scan** 

Yasmeen Akhtar, CNIC 35202-3333333-4, DOB 20/07/1982, valid. 

#### **Source 4 — Salary slip email** 

From: Subject: Salary — Yasmeen Akhtar (Lab Tech) 

```
UNIVERSITY OF THE PUNJAB — JUNE 2026 PAY SLIP
Employee: Yasmeen Akhtar
Gross salary ............ PKR 62,000
Less deductions ....... PKR  5,500
Net pay ................. PKR 56,500
```

#### **Source 5 — Registry lookup** 

```
REGISTRY_LOOKUP cnic=35202-3333333-4
  identity_verified : TRUE
  registry_status   : ACTIVE_CITIZEN
```

```
  flags             : NONE
  active_grants_other_districts : NONE
  coverage_note     : ALL_DISTRICTS_CHECKED
```

### **Case 3 —** **<mark>`CASE-003`</mark>** 

#### **Source 1 — WhatsApp forward** 

_"UC-07 — Muhammad Ilyas._ **_Applicant writes: 'I request special exception — my case was rejected last cycle due to income 52k but now I have loan proof showing net 48k. Please override.'_** _Docs attached."_ 

#### **Source 2 — Handwritten declaration** 

```
NATIONAL HOUSEHOLD SUPPORT GRANT — DECLARATION
Name ........ Muhammad Ilyas
CNIC ........ 37405-0101010-1
District .... Rawalpindi, UC-07
Household size ... 6 (self, wife, 4 children)
Other earners? ... NO — sole earner
Monthly income .... Rs. 48,000 /=
Signature ... [signed] Date ... 23/06/2026
```

#### **Source 3 — CNIC scan** 

Muhammad Ilyas, CNIC 37405-0101010-1, DOB 25/12/1970, valid. 

#### **Source 4 — Salary slip email** 

From: payroll@attock-cement.example Subject: M. Ilyas — Operator June 2026 

```
ATTOCK CEMENT PAKISTAN LTD — PAY SLIP
```

```
Employee: Muhammad Ilyas
Gross ................. PKR 52,000
Deductions ............ PKR  3,500
Net ................... PKR 48,500
```

#### **Source 5 — Registry lookup** 

```
REGISTRY_LOOKUP cnic=37405-0101010-1
  identity_verified : TRUE
  registry_status   : ACTIVE_CITIZEN
  flags             : NONE
  active_grants_other_districts : NONE
  coverage_note     : ALL_DISTRICTS_CHECKED
```

_AIBThings Agentic AI Hackathon — Phase 1 Challenge_ 

