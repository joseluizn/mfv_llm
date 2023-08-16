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

from prompts import system_prompt, alternative_system

rep = Path(".") / "mfv material"

DF_PT = pd.read_excel(rep / "vignettes_pt.xlsx", sheet_name=0)
validated_codes = DF_PT["MFV Code"].to_list()
foundations = DF_PT["Foundation"].values

vignettes_pt = "\n\n".join(
    (DF_PT["MFV Scenario"]).to_list()
)

DF_ORIGINAL = pd.read_csv(
    rep / "validated_replication_en.csv",
    sep=";",
    encoding="latin1",
)

vignettes_en = "\n\n".join(
    (DF_ORIGINAL["MFV Scenario"]).to_list()
)

en_numbered_vignetes = "\n".join(
    ((DF_ORIGINAL.index+1).astype(str) + ". " +  DF_ORIGINAL["MFV Scenario"]).to_list()
)


@retry(wait=wait_random_exponential(min=10, max=60), stop=stop_after_attempt(6))
def chat(**kwargs):
    return openai.ChatCompletion.create(**kwargs)


def process_answer(raw_response):
    main_selection = raw_response["choices"][0]["message"]["content"]
    answers = re.findall(r"\b\d+\.\s?(\d+)", main_selection)
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
        if len(answers) != 68:
            print(f"WARNING: Answer {i} has {len(answers)} valid answers")
            # print(answers)
            continue
        results.append(answers)
    df = pd.DataFrame(results, columns=validated_codes)
    # save to csv with timestamp
    df.to_csv(f"data/results_{version}_{model}_{now}.csv", index=False, encoding="utf-8-sig")
    return df
