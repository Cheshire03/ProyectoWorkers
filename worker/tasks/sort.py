import pandas as pd


def run(df: pd.DataFrame, params: dict) -> dict:
    """
    Ordena el CSV por una o varias columnas.
    params esperados:
        - columna: str o list[str]
        - ascendente: bool (default True)
    """
    columna     = params.get("columna")
    ascendente  = params.get("ascendente", True)

    if not columna:
        return {"error": "Debes enviar 'columna' en los parámetros."}

    columnas = columna if isinstance(columna, list) else [columna]

    # Validar que las columnas existen
    faltantes = [c for c in columnas if c not in df.columns]
    if faltantes:
        return {
            "error": f"Columnas no encontradas: {faltantes}",
            "columnas_disponibles": list(df.columns),
        }

    try:
        ordenado = df.sort_values(by=columnas, ascending=ascendente)

        return {
            "operacion": "sort",
            "ordenado_por": columnas,
            "ascendente": ascendente,
            "total_filas": len(ordenado),
            "datos": ordenado.head(500).to_dict(orient="records"),  # max 500 filas
        }

    except Exception as e:
        return {"error": str(e)}