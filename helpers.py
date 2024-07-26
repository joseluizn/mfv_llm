import numpy as np

def cohen_d(x,y):
        from math import sqrt
        std_factor = sqrt((np.std(x, ddof=1) ** 2 + np.std(y, ddof=1) ** 2) / 2.0)
        if std_factor == 0:
            return np.nan
        return (np.mean(x) - np.mean(y))