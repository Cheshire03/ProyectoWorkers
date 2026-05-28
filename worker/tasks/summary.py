import pandas as pd


def run(df: pd.DataFrame) -> dict:
    """
    Genera un resumen general del CSV:
    dimensiones, tipos, muestra, valores únicos.
    """
    resumen_columnas = {}
    for col in df.columns:
        serie = df[col]
        resumen_columnas[col] = {
            "tipo":          str(serie.dtype),
            "nulos":         int(serie.isnull().sum()),
            "unicos":        int(serie.nunique()),
            "muestra":       serie.dropna().head(3).tolist(),
        }

    return {
        "operacion":      "summary",
        "total_filas":    len(df),
        "total_columnas": len(df.columns),
        "columnas":       list(df.columns),
        "memoria_kb":     round(df.memory_usage(deep=True).sum() / 1024, 2),
        "duplicados":     int(df.duplicated().sum()),
        "detalle":        resumen_columnas,
    }