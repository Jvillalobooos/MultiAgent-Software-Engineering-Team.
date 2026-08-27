"""Web interface for the calculator using Streamlit."""

import streamlit as st
from calculadora import operaciones

OPERATIONS = {
    "sumar": ("Sumar", operaciones.sumar),
    "restar": ("Restar", operaciones.restar),
    "multiplicar": ("Multiplicar", operaciones.multiplicar),
    "dividir": ("Dividir", operaciones.dividir),
    "potencia": ("Potencia", operaciones.potencia),
    "raiz": ("Raíz", operaciones.raiz),
    "porcentaje": ("Porcentaje", operaciones.porcentaje),
}

def main() -> None:
    st.title("Calculadora")
    st.write("Seleccione una operación y proporcione los números requeridos.")

    operation_key = st.selectbox(
        "Operación",
        options=list(OPERATIONS.keys()),
        format_func=lambda k: OPERATIONS[k][0],
    )
    func = OPERATIONS[operation_key][1]

    if operation_key == "raiz":
        num1 = st.number_input("Número", value=0.0, step=0.1)
        inputs = (num1,)
    else:
        num1 = st.number_input("Número 1", value=0.0, step=0.1)
        num2 = st.number_input("Número 2", value=0.0, step=0.1)
        inputs = (num1, num2)

    if st.button("Calcular"):
        try:
            result = func(*inputs)
            st.success(f"Resultado: {result}")
        except Exception as e:
            st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
