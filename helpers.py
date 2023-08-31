import re
import json

import pandas as pd
from pathlib import Path
import openai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)  # for exponentia

from prompts import system_prompt, alternative_system, simple_system, pre_mfv

rep = Path(".") / "mfv material"

DF_PT = pd.read_excel(rep / "vignettes_pt.xlsx", sheet_name=0)
validated_codes = DF_PT["MFV Code"].to_list()
foundations = DF_PT["Foundation"].values

original_validated = pd.read_html("https://link.springer.com/article/10.3758/s13428-014-0551-2/tables/6")[0]
original_validated["mfv_code"] = [101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,201,202,203,204,205,206,207,208,301,302,303,401,402,403,404,405,406,407,408,409,410,411,412,501,502,503,504,505,506,507,508,509,510,511,601,602,603,604,605,606,607,608,609,610,611,612,613,614,701,702,703,704,705,706,707,708,709,710,711,712,713,714,715,716,801,802,803,804,805,806,807,808,809,810]
# query for validated codes
original_validated.query("mfv_code in @validated_codes", inplace=True)

vignettes_pt = "\n\n".join(
    (DF_PT["MFV Scenario"]).to_list()
)

DF_BACK_TRANSLATION = pd.read_csv(
    rep / "validated_replication_en.csv",
    sep=";",
    encoding="latin1",
)

vignettes_en = "\n\n".join(
    (DF_BACK_TRANSLATION["MFV Scenario"]).to_list()
)

original_numbered = "\n".join(
    ((original_validated.reset_index().index+1).astype(str) + ". " + original_validated["Scenario"]).to_list()
)

en_numbered_vignetes = "\n".join(
    ((DF_BACK_TRANSLATION.index+1).astype(str) + ". " + DF_BACK_TRANSLATION["MFV Scenario"]).to_list()
)


@retry(wait=wait_random_exponential(min=10, max=60), stop=stop_after_attempt(6))
def chat(**kwargs):
    return openai.ChatCompletion.create(**kwargs)


def process_answer(raw_response):
    main_selection = raw_response["choices"][0]["message"]["content"]
    answers = re.findall(r"\b\d+\.\s?(\d+)", main_selection)
    if len(answers) == 0:
        # this case should be single scenario generation
        answers = re.findall(r"^\b\d\b$", main_selection)
    answers = [int(i) for i in answers]
    return answers


def mfv_experiment(model, system_prompt, vignettes, **kwargs):
    msg_hist = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": vignettes},
    ]
    raw_response = chat(
        messages=msg_hist,
        model=model,
        max_tokens=1024,
        temperature=1.2,
        **kwargs,
    )
    return raw_response


def run_n_experiments(n, model, version="original"):
    results_raw = []
    if version == "original":
        system = system_prompt
        vignettes = en_numbered_vignetes
        # print("This prompt was dropped in a previous version. interrupting experiment....")
        # return None
    elif version == "alternative":
        system = alternative_system
        vignettes = en_numbered_vignetes
        print("This prompt was dropped in a previous version. interrupting experiment....")
        return None
    for i in range(n):
        results_raw.append(
            (
                i+1,
                mfv_experiment(
                    model,
                    system_prompt=system,
                    vignettes=vignettes,
                ),
            )
        )
    # save results to json including timestamp
    now = pd.Timestamp.now().strftime('%Y-%m-%d_%H-%M')
    with open(
        f"data/raw/raw_results_{version}_{now}.json",
        "w",
    ) as f:
        json.dump(results_raw, f)
    results = list()
    for i, r in results_raw:
        answers = process_answer(r)
        if len(answers) != 68 and len(answers) != 1:
            print(f"WARNING: Answer {i} has {len(answers)} valid answers")
            print(answers)
            continue
        results.append(answers)
    df = pd.DataFrame(results, columns=validated_codes)
    # save to csv with timestamp
    df.to_csv(f"data/results_{version}_{model}_{now}.csv", index=False, encoding="utf-8-sig")
    return df


def run_single_scenario(vignette, model, **kwargs):
    msg_hist = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": vignette},
    ]
    # print(msg_hist)
    raw_response = chat(
        messages=msg_hist,
        model=model,
        max_tokens=1024,
        temperature=1.2,
        **kwargs,
    )
    return raw_response


def single_scenario_generation(scenario, model, n_experiments=108, **kwargs):
    vignette, mfv_code = scenario

    responses = list()
    for i in range(n_experiments):
        raw_response = run_single_scenario(
            vignette="1. "+ vignette,
            model=model,
            **kwargs,
        )
        responses.append((i+1, raw_response))

    now = pd.Timestamp.now().strftime('%Y-%m-%d_%H-%M')
    with open(
        f"data/raw/raw_results_{mfv_code}_{model}_{now}.json",
        "w",
    ) as f:
        json.dump(responses, f)

    gen_answers = list()
    for i, r in enumerate(responses):
        answers = process_answer(raw_response)
        if len(answers) > 1 or len(answers) == 0:
            print(f"WARNING: Answer {i+1} has {len(answers)} valid answers")
            continue
        else:
            gen_answers.append((i+1, answers[0]))

    df = pd.DataFrame(gen_answers, columns=["gen_id", "answer"])

    df["mfv_code"] = mfv_code
    df["model"] = model
    df.to_csv(f"data/results_scenario_{mfv_code}_{model}_{now}.csv", index=False)
    return df


def run_random_order(n, model, version="backtrans", **kwargs):
    answers = list()
    if version == "backtrans":
        df_scenarios = original_validated
    for i in range(n):
        shuffled_scenarios = df_scenarios.sample(frac=1)
        shuffled_scenarios.reset_index(drop=True, inplace=True)
        scenario_order = shuffled_scenarios["mfv_code"].to_list()
        numbered_scenarios = "\n".join(
            ((shuffled_scenarios.index+1).astype(str) + ". " +  shuffled_scenarios["Scenario"]).to_list()
        )
        raw_answer = mfv_experiment(model, system_prompt, numbered_scenarios, **kwargs)
        answers.append({"response": raw_answer, "scenario_order": scenario_order})
    now = pd.Timestamp.now().strftime('%Y-%m-%d_%H-%M')
    p = Path(f"data/raw/random_order")
    p.mkdir(exist_ok=True)
    with open(
        p / f"raw_results_{model}_{now}.json",
        "w",
    ) as f:
        json.dump(answers, f)

    results = list()
    for i, a in enumerate(answers):
        mfv_answers = process_answer(a["response"])
        if len(mfv_answers) != 68 and len(mfv_answers) != 1:
            print(f"WARNING: Answer {i} has {len(mfv_answers)} valid answers")
            print(mfv_answers)
            continue
        _df = pd.DataFrame(data=[mfv_answers], columns=a["scenario_order"])
        results.append(_df)
    df = pd.concat(results)
    df = df.reindex(sorted(df.columns), axis=1)
    p = Path(f"data/random_order")
    p.mkdir(exist_ok=True)
    df.to_csv(p/"/results_{model}_{now}.csv", index=False, encoding="utf-8-sig")
    return df
