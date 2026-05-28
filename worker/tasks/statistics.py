import pandas as pd
import json


def run(df: pd.DataFrame) -> dict:
    """
    Calcula estadísticas por columna numérica:
    promedio, mínimo, máximo, total, desviación estándar.
    """
    result = {}
    numeric_cols = df.select_dtypes(include="number").columns

    if len(numeric_cols) == 0:
        return {"error": "No se encontraron columnas numéricas en el CSV."}

    for col in numeric_cols:
        series = df[col].dropna()
        result[col] = {
            "promedio": round(series.mean(), 4),
            "total":    round(series.sum(), 4),
            "minimo":   round(series.min(), 4),
            "maximo":   round(series.max(), 4),
            "std":      round(series.std(), 4),
            "count":    int(series.count()),
        }

    return {
        "operacion": "statistics",
        "total_filas": len(df),
        "columnas_analizadas": list(numeric_cols),
        "resultados": result,
    }