import pandas as pd


def run(df: pd.DataFrame) -> dict:
    """
    Detecta filas inválidas:
    - Filas completamente vacías
    - Filas con valores nulos por columna
    - Columnas con tipos mixtos
    """
    total_filas = len(df)

    # Filas completamente vacías
    filas_vacias = df[df.isnull().all(axis=1)].index.tolist()

    # Nulos por columna
    nulos_por_columna = df.isnull().sum().to_dict()
    nulos_por_columna = {k: int(v) for k, v in nulos_por_columna.items() if v > 0}

    # Filas con al menos un nulo
    filas_con_nulos = df[df.isnull().any(axis=1)].index.tolist()

    # Tipos detectados por columna
    tipos = {col: str(df[col].dtype) for col in df.columns}

    # Duplicados
    duplicados = int(df.duplicated().sum())

    return {
        "operacion": "validate",
        "total_filas": total_filas,
        "total_columnas": len(df.columns),
        "filas_vacias": len(filas_vacias),
        "indices_filas_vacias": filas_vacias[:50],  # max 50 para no saturar
        "filas_con_nulos": len(filas_con_nulos),
        "indices_filas_con_nulos": filas_con_nulos[:50],
        "nulos_por_columna": nulos_por_columna,
        "filas_duplicadas": duplicados,
        "tipos_de_datos": tipos,
        "porcentaje_valido": round(
            (total_filas - len(filas_con_nulos)) / total_filas * 100, 2
        ) if total_filas > 0 else 0,
    }