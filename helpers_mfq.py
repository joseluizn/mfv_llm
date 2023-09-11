import json
import pandas as pd
from pathlib import Path

from helpers import chat, original_numbered
from prompts import simple_system, pre_mfv

mfq_part1 = """
When you decide whether something is right or wrong, to what extent are the following considerations relevant to your thinking? Please rate each statement using this scale:

[0] = not at all relevant (This consideration has nothing to do with my judgments of right and wrong)
[1] = not very relevant
[2] = slightly relevant
[3] = somewhat relevant
[4] = very relevant
[5] = extremely relevant (This is one of the most important factors when I judge right and wrong)

1. Whether or not someone suffered emotionally
2. Whether or not some people were treated differently than others
3. Whether or not someone’s action showed love for his or her country
4. Whether or not someone showed a lack of respect for authority
5. Whether or not someone violated standards of purity and decency
6. Whether or not someone was good at math
7. Whether or not someone cared for someone weak or vulnerable
8. Whether or not someone acted unfairly
9. Whether or not someone did something to betray his or her group
10. Whether or not someone conformed to the traditions of society
11. Whether or not someone did something disgusting
12. Whether or not someone was cruel
13. Whether or not someone was denied his or her rights
14. Whether or not someone showed a lack of loyalty
15. Whether or not an action caused chaos or disorder
16. Whether or not someone acted in a way that God would approve of
"""

mfq_part2 = """
Please read the following sentences and indicate your agreement or disagreement:

[0] = Strongly disagree
[1] = Moderately disagree
[2] = Slightly disagree
[3] = Slightly agree
[4] = Moderately agree
[5] = Strongly agree

17. Compassion for those who are suffering is the most crucial virtue.
18. When the government makes laws, the number one principle should be ensuring that everyone is treated fairly.
19. I am proud of my country’s history.
20. Respect for authority is something all children need to learn.
21. People should not do things that are disgusting, even if no one is harmed.
22. It is better to do good than to do bad.
23. One of the worst things a person could do is hurt a defenseless animal.
24. Justice is the most important requirement for a society.
25. People should be loyal to their family members, even when they have done something wrong.
26. Men and women each have different roles to play in society.
27. I would call some acts wrong on the grounds that they are unnatural.
28. It can never be right to kill a human being.
29. I think it’s morally wrong that rich children inherit a lot of money while poor children inherit nothing.
30. It is more important to be a team player than to express oneself.
31. If I were a soldier and disagreed with my commanding officer’s orders, I would obey anyway because that is my duty.`
32. Chastity is an important and valuable virtue.
"""

questions1_item_key = [
    ("emotionally", "harm"),
    ("treated", "fairness"),
    ("lovecountry", "ingroup"),
    ("respect", "authority"),
    ("decency", "purity"),
    ("math", None),
    ("weak", "harm"),
    ("unfairly", "fairness"),
    ("betray", "ingroup"),
    ("traditions", "authority"),
    ("disgusting", "purity"),
    ("cruel", "harm"),
    ("rights", "fairness"),
    ("loyalty", "ingroup"),
    ("chaos", "authority"),
    ("god", "purity"),
]

questions2_item_key = [
    ("compassion", "harm"),
    ("fairly", "fairness"),
    ("history", "ingroup"),
    ("kidrespect", "authority"),
    ("harmlessdg", "purity"),
    ("good", None),
    ("animal", "harm"),
    ("justice", "fairness"),
    ("family", "ingroup"),
    ("sexroles", "authority"),
    ("unnatural", "purity"),
    ("kill", "harm"),
    ("rich", "fairness"),
    ("team", "ingroup"),
    ("soldier", "authority"),
    ("chastity", "purity"),
]


def mfq_experiment(model, msg_hist, **kwargs):
    msg_hist.append(
        {"role": "user", "content": mfq_part1},
    )
    raw_part1 = chat(
        messages=msg_hist,
        model=model,
        max_tokens=1024,
        temperature=1.0,
        **kwargs,
    )
    msg_hist.append(
        {"role": "system", "content": raw_part1["choices"][0]["message"]["content"]},
    )
    msg_hist.append(
        {"role": "user", "content": mfq_part2},
    )

    raw_part2 = chat(
        messages=msg_hist,
        model=model,
        max_tokens=1024,
        temperature=1.0,
        **kwargs,
    )
    msg_hist.append(
        {"role": "system", "content": raw_part2["choices"][0]["message"]["content"]},
    )
    return raw_part1, raw_part2, msg_hist


def run_mfv_mfq(model, mfv_how="after", mfv="original", **kwargs):
    msg_hist = [
        {"role": "system", "content": simple_system},
        ]
        
    if mfv == "original":
        vignettes = pre_mfv + "\n\n" + original_numbered
    else:
         raise("Not implemented for this MFV value.")
    if mfv_how == "after":
        raw_1, raw_2, msg_hist = mfq_experiment(model, msg_hist, **kwargs)
        msg_hist.append(
            {"role": "user", "content": vignettes},
        )

        raw_mfv = chat(
            messages=msg_hist,
            model=model,
            max_tokens=1024,
            temperature=1.0,
            **kwargs,
        )
        return raw_1, raw_2, raw_mfv
    elif mfv_how == "before":
        msg_hist.append(
            {"role": "user", "content": vignettes},
        )
        raw_mfv = chat(
            messages=msg_hist,
            model=model,
            max_tokens=1024,
            temperature=1.0,
            **kwargs,
        )
        msg_hist.append(
             {"role": "system", "content": raw_mfv["choices"][0]["message"]["content"]},
        )

        raw_1, raw_2, msg_hist = mfq_experiment(model, msg_hist, **kwargs)
        return raw_1, raw_2, raw_mfv


def generate_mfq_before_after(model, n):
    raws_before = []
    for i in range(n):
        raws_before.append(run_mfv_mfq(model, mfv_how="before", mfv="original"))
    p = Path("data/raw/mfq")
    p.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now().strftime('%Y-%m-%d_%H-%M')
    with open(p / f"before_{model}_{now}.json", "w") as f:
        json.dump(raws_before, f)

    raws_after = []
    for i in range(n):
        raws_after.append(run_mfv_mfq(model, mfv_how="after", mfv="original"))
    with open(p / f"after_{model}_{now}.json", "w") as f:
        json.dump(raws_after, f)
    return raws_before, raws_after


def process_mfq(raws_before, raws_after, model):
    from pathlib import Path
    from helpers import validated_codes, process_answer
    # processing answers for each generation
    processed_before = list()
    for i, raws in enumerate(raws_before):
        mfq1, mfq2, mfv = map(process_answer, raws)
        if len(mfq1) != 16 or len(mfq2) != 16:
            print(f"Skipping {i + 1}: MFQ Part 1 has {len(mfq1)} answers and Part 2 has {len(mfq2)} answers.")
            continue
        elif len(mfv) != 68:
            print(f"Skipping {i + 1}: MFV has {len(mfv)} answers.")
            continue
        _row = [i + 1, "before"]
        _row.extend(mfq1)
        _row.extend(mfq2)
        _row.extend(mfv)
        processed_before.append(_row)

    processed_after = list()
    for i, raws in enumerate(raws_after):
        mfq1, mfq2, mfv = map(process_answer, raws)
        if len(mfq1) != 16 or len(mfq2) != 16:
            print(f"Skipping {i + 1}: MFQ Part 1 has {len(mfq1)} answers and Part 2 has {len(mfq2)} answers.")
            continue
        elif len(mfv) != 68:
            print(f"Skipping {i + 1}: MFV has {len(mfv)} answers.")
            continue
        _row = [i + 1, "after"]
        _row.extend(mfq1)
        _row.extend(mfq2)
        _row.extend(mfv)
        processed_after.append(_row)
    
    df = pd.DataFrame(
        processed_before + processed_after,
        columns=["id", "condition"] + [x[0] for x in questions1_item_key] + [x[0] for x in questions2_item_key] + validated_codes
    )
    p = Path("data")/"mfq"
    p.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now().strftime("%Y-%m-%d_%H-%M-%S")
    df.to_csv(p/f"mfq_experiment_{model}_{now}.csv", index=False)
    return df
