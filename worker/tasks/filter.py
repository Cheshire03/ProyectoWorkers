import pandas as pd


def run(df: pd.DataFrame, params: dict) -> dict:
    """
    Filtra filas según condición.
    params esperados:
        - columna: str
        - operador: '>', '<', '>=', '<=', '==', '!='
        - valor: cualquier valor
    """
    columna  = params.get("columna")
    operador = params.get("operador", "==")
    valor    = params.get("valor")

    if not columna or valor is None:
        return {"error": "Debes enviar 'columna' y 'valor' en los parámetros."}

    if columna not in df.columns:
        return {"error": f"La columna '{columna}' no existe en el CSV.", "columnas_disponibles": list(df.columns)}

    try:
        # Intentar convertir valor al tipo de la columna
        col_dtype = df[columna].dtype
        if pd.api.types.is_numeric_dtype(col_dtype):
            valor = float(valor)

        ops = {
            ">":  df[columna] > valor,
            "<":  df[columna] < valor,
            ">=": df[columna] >= valor,
            "<=": df[columna] <= valor,
            "==": df[columna] == valor,
            "!=": df[columna] != valor,
        }

        if operador not in ops:
            return {"error": f"Operador '{operador}' no válido. Usa: >, <, >=, <=, ==, !="}

        filtrado = df[ops[operador]]

        return {
            "operacion": "filter",
            "condicion": f"{columna} {operador} {valor}",
            "total_filas_original": len(df),
            "total_filas_filtradas": len(filtrado),
            "datos": filtrado.head(500).to_dict(orient="records"),  # max 500 filas
        }

    except Exception as e:
        return {"error": str(e)}