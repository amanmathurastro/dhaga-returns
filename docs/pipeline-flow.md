# How the pipeline code flows

Read this next to `backend/app/pipeline/run.py`. Every box names the function that does the step.

Legend: gray = plain code, purple = model call (LangChain), coral = failure bucket.

## 1. What happens when "Run pipeline" is pressed

```mermaid
flowchart TD
    BTN["Button on the Summary page<br/>frontend/components/RunControl.tsx"] -->|POST /pipeline/run| START["start_run()<br/>routers/pipeline.py"]
    START --> CREATE["db.create_run()<br/>inserts a row with status 'running'"]
    CREATE --> BG["execute_run()<br/>pipeline/run.py, runs in the background"]
    BG --> LOAD["1. Load tables from the database<br/>db.fetch_returns / fetch_order_lines / fetch_skus / fetch_vendors / fetch_sales"]
    LOAD --> BUILD["2. Build the three model functions<br/>build_classifier(A), build_classifier(B), build_brief_writer(B)"]
    BUILD --> PROCESS["3. process()<br/>the whole chain, see diagram 2"]
    PROCESS --> SAVE["4. Save results<br/>db.save_classifications, db.save_briefs, db.finish_run('done')"]
    BG -. any error .-> FAIL["db.finish_run('failed', error)"]

    classDef code fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef model fill:#EEEDFE,stroke:#534AB7,color:#26215C;
    classDef fail fill:#FAECE7,stroke:#993C1D,color:#4A1B0C;
    class BTN,START,CREATE,BG,LOAD,PROCESS,SAVE code;
    class BUILD model;
    class FAIL fail;
```

## 2. Inside `process()` (pipeline/run.py)

```mermaid
flowchart TD
    A["Keep only 'Other' returns<br/>is_other() in load.py"] --> B["Join return -> order line -> SKU -> vendor<br/>join_returns() in load.py"]
    B --> P["Keep returns inside the period<br/>in_period() in load.py"]
    P -->|no vendor found| U["unmatched"]
    P --> C["Remove phone numbers and emails<br/>scrub_pii() in filters.py"]
    C --> D["Is it junk?<br/>junk_reason() in filters.py"]
    D -->|blank, 'ok', emoji| J["junk"]
    D -->|real comment| R["route() in classify.py<br/>run for many comments at once (thread pool)"]

    subgraph ROUTE["route(): one comment"]
        R1["Model A classifies<br/>attempt('A', ...)"] -->|valid and confident| OK["classified"]
        R1 -->|failed, invalid, or below CONFIDENCE_THRESHOLD| R2["Model B classifies<br/>attempt('B', ...)"]
        R2 -->|valid and confident| OK
        R2 -->|failed or still unsure| X["unclassified"]
    end
    R --> R1

    OK --> AGG["Rates, category averages, flags<br/>aggregate() in aggregate.py"]
    AGG --> BI["Pick vendors with a flag, collect their numbers and comments<br/>brief_inputs() in run.py"]
    BI --> W["Model B writes the brief<br/>write_brief() in brief.py"]
    W --> CHK["Check every number against the table<br/>check_brief() in brief.py"]
    CHK -->|all match| BOK["brief: ok"]
    CHK -->|a number is wrong| BREJ["brief: rejected_numbers_mismatch"]
    W -. model error .-> BFAIL["brief: failed"]

    classDef code fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef model fill:#EEEDFE,stroke:#534AB7,color:#26215C;
    classDef fail fill:#FAECE7,stroke:#993C1D,color:#4A1B0C;
    class A,B,P,C,D,R,OK,AGG,BI,CHK,BOK code;
    class R1,R2,W model;
    class U,J,X,BREJ,BFAIL fail;
```

## 3. Inside one model call (the LangChain chain)

Built once by `structured_call()` in `classify.py`, used for both classification and the brief.

```mermaid
flowchart LR
    T["comment text"] --> PR["prompt<br/>ChatPromptTemplate<br/>system prompt + the comment"]
    PR --> M["model<br/>ChatOpenAI via OpenRouter<br/>schema sent as a forced tool call"]
    M --> RES["_to_result<br/>RunnableLambda<br/>validates, counts tokens, or raises"]
    RES --> OUT["LLMResult<br/>(ReturnClassification or VendorBrief)"]

    classDef code fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    classDef model fill:#EEEDFE,stroke:#534AB7,color:#26215C;
    class T,PR,RES,OUT code;
    class M model;
```

## 4. How a dashboard page gets its numbers

Nothing is calculated in the browser, and no model is called when a page loads.

```mermaid
flowchart LR
    PAGE["A page, e.g. /vendors"] -->|GET /vendors| RT["router<br/>routers/vendors.py"]
    RT --> VIEW["load_run_view()<br/>reporting.py<br/>reads the latest finished run"]
    VIEW --> AGG2["aggregate() again<br/>same function the run used"]
    AGG2 --> JSON["JSON back to the page"]

    classDef code fill:#F1EFE8,stroke:#5F5E5A,color:#2C2C2A;
    class PAGE,RT,VIEW,AGG2,JSON code;
```

## Which file to open for what

| Question | File |
|---|---|
| What order do the steps run in? | `pipeline/run.py` (`process`) |
| How is a return linked to a vendor? | `pipeline/load.py` |
| What counts as junk? What is scrubbed? | `pipeline/filters.py` |
| What does the model get asked? How does A hand over to B? | `pipeline/classify.py` |
| How are rates and flags calculated? | `pipeline/aggregate.py` |
| How is the brief written and checked? | `pipeline/brief.py` |
| What shape must the model's answer have? | `schemas.py` |
| Which reasons exist and who owns each? | `taxonomy.py` |
| All SQL | `db.py` |
