import pandas as pd
from factor_analyzer import FactorAnalyzer
from factor_analyzer.factor_analyzer import calculate_kmo

from helpers import vignettes_en, foundations, validated_codes


def run_factor_analysis(df, n_factors=7, method="ml", return_model=False):
    # identifying columns with no variation
    cae = df.nunique()[df.nunique() == 1].index.to_list()
    # convert to int
    if len(cae) > 0:
        print(f"Columns with no variation: {cae}.\nDropping.....")
        df = df.drop(columns=cae)

    # run kmo
    kmo_all, kmo_model = calculate_kmo(df)
    print(f"KMO: {kmo_model}")

    exploratory_fa = FactorAnalyzer(
        n_factors=n_factors,
        rotation="promax",
        method=method,
        # method="ml", # this is the original, but it doesn't converge for gpt4
    )
    exploratory_fa.fit(df)

    # print cumulative variance explained
    vars = exploratory_fa.get_factor_variance()
    print(f"Cumulative variance explained by {n_factors} factors: {vars[2][-1]}")
    print("Variance:", vars[1])

    factor_df = pd.DataFrame(
        exploratory_fa.loadings_,
        columns=[
            "Factor 1",
            "Factor 2",
            "Factor 3",
            "Factor 4",
            "Factor 5",
            "Factor 6",
            "Factor 7",
        ],
    )

    info_df = pd.DataFrame(
        {
            "MFV Code": validated_codes,
            "MFV Scenario": vignettes_en.split("\n\n"),
            "Foundation": foundations,
        }
    )
    cae_int = [int(x) for x in cae]
    info_df.query(
        "`MFV Code` not in @cae and `MFV Code` not in @cae_int",
        inplace=True,
    )

    factor_df = pd.concat([info_df, factor_df], axis=1)
    if return_model is True:
        return factor_df, exploratory_fa
    return factor_df
