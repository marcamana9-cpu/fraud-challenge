"""
Interface Streamlit — À CRÉER PAR VOUS pour le jury.

Le jury lancera :  streamlit run app.py

Règles :
  - Ne modifiez pas l'appel à detect_fraud / load_transactions (contrat technique).
  - Personnalisez render_interface() : clarté, intuitivité, compréhension pour un public non technique.
  - L'interface n'est PAS notée par la CI ; elle sert au jury pour repêcher et comparer les candidats.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from fraud_detection import detect_fraud, load_transactions

SAMPLE_CSV = Path(__file__).parent / "data" / "sample_transactions.csv"


def render_interface(transactions: list[dict], results: list[dict]) -> None:
    """
    Affiche une synthèse lisible des alertes pour le jury et un public non technique.
    """
    tx_df = pd.DataFrame(transactions)
    res_df = pd.DataFrame(results)

    if tx_df.empty or res_df.empty:
        st.info("Aucune transaction à analyser.")
        return

    dashboard = pd.concat(
        [
            tx_df.reset_index(drop=True),
            res_df.drop(columns=["transaction_id"], errors="ignore").reset_index(drop=True),
        ],
        axis=1,
    )
    dashboard["risk_level"] = dashboard["fraud_score"].apply(_risk_level)

    alert_count = int(dashboard["is_suspicious"].sum())
    total_count = len(dashboard)
    alert_rate = alert_count / total_count if total_count else 0
    average_score = float(dashboard["fraud_score"].mean()) if total_count else 0.0
    max_score = float(dashboard["fraud_score"].max()) if total_count else 0.0

    st.header("Tableau de bord anti-fraude")
    st.write(
        "Cette interface explique les alertes générées par le détecteur : "
        "montants anormaux, pays incohérents, transactions rapprochées ou données manquantes."
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Transactions analysées", total_count)
    col2.metric("Alertes", alert_count)
    col3.metric("Taux d'alerte", f"{alert_rate:.0%}")
    col4.metric("Risque maximum", f"{max_score:.2f}")

    st.progress(min(average_score, 1.0), text=f"Risque moyen du lot : {average_score:.2f}")

    tab_alerts, tab_all, tab_clients, tab_explain = st.tabs([
        "Alertes prioritaires",
        "Toutes les transactions",
        "Clients à surveiller",
        "Comment lire le score",
    ])

    with tab_alerts:
        suspicious = dashboard[dashboard["is_suspicious"]].sort_values(
            "fraud_score",
            ascending=False,
        )

        if suspicious.empty:
            st.success("Aucune transaction suspecte détectée dans ce lot.")
        else:
            st.warning(f"{len(suspicious)} transaction(s) à vérifier en priorité.")
            st.dataframe(
                _display_columns(suspicious),
                use_container_width=True,
                hide_index=True,
                column_config=_column_config(),
            )

            reason_counts = suspicious["reason"].value_counts()
            st.subheader("Principales causes d'alerte")
            st.bar_chart(reason_counts)

    with tab_all:
        users = sorted(dashboard.get("user_id", pd.Series(dtype=str)).dropna().unique().tolist())
        selected_user = st.selectbox("Filtrer par client", ["Tous"] + users)
        show_only_alerts = st.toggle("Afficher seulement les alertes", value=False)

        filtered = dashboard.copy()
        if selected_user != "Tous":
            filtered = filtered[filtered["user_id"] == selected_user]
        if show_only_alerts:
            filtered = filtered[filtered["is_suspicious"]]

        st.dataframe(
            _display_columns(filtered),
            use_container_width=True,
            hide_index=True,
            column_config=_column_config(),
        )

    with tab_clients:
        if "user_id" not in dashboard.columns:
            st.info("Aucun identifiant client disponible pour cette analyse.")
        else:
            client_summary = (
                dashboard.groupby("user_id", dropna=False)
                .agg(
                    transactions=("transaction_id", "count"),
                    alertes=("is_suspicious", "sum"),
                    risque_moyen=("fraud_score", "mean"),
                    risque_max=("fraud_score", "max"),
                )
                .reset_index()
                .sort_values(["alertes", "risque_max"], ascending=False)
            )
            st.dataframe(
                client_summary,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "risque_moyen": st.column_config.ProgressColumn(
                        "Risque moyen",
                        min_value=0.0,
                        max_value=1.0,
                        format="%.2f",
                    ),
                    "risque_max": st.column_config.ProgressColumn(
                        "Risque max",
                        min_value=0.0,
                        max_value=1.0,
                        format="%.2f",
                    ),
                },
            )

    with tab_explain:
        st.subheader("Règles utilisées")
        st.markdown(
            """
            - **0.75 et plus** : transaction signalée comme suspecte.
            - **Montant anormal** : comparaison avec l'historique du même client et de la même devise.
            - **Pays incohérent** : deux pays différents sur un délai trop court.
            - **Fréquence élevée** : plusieurs paiements rapprochés, surtout avec commerçants ou pays différents.
            - **Données manquantes** : une transaction incomplète mérite une vérification humaine.
            """
        )
        st.info(
            "Objectif : signaler les cas réellement risqués tout en évitant de bloquer "
            "un client honnête pour une transaction seulement inhabituelle."
        )


def _risk_level(score: float) -> str:
    if score >= 0.75:
        return "Élevé"
    if score >= 0.4:
        return "À surveiller"
    return "Faible"


def _display_columns(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "transaction_id",
        "user_id",
        "timestamp",
        "amount",
        "currency",
        "merchant",
        "country",
        "card_present",
        "fraud_score",
        "risk_level",
        "is_suspicious",
        "reason",
    ]
    return df[[column for column in columns if column in df.columns]]


def _column_config() -> dict:
    return {
        "fraud_score": st.column_config.ProgressColumn(
            "Score de risque",
            min_value=0.0,
            max_value=1.0,
            format="%.2f",
        ),
        "is_suspicious": st.column_config.CheckboxColumn("Suspecte"),
        "risk_level": st.column_config.TextColumn("Niveau"),
        "reason": st.column_config.TextColumn("Justification"),
    }


def main() -> None:
    st.set_page_config(
        page_title="Détection de fraude — Hackathon INTELO2026",
        page_icon="🛡️",
        layout="wide",
    )

    st.title("Détection de fraude financière")
    st.caption("Hackathon INTELO2026 — interface participant · évaluée par le jury")

    with st.sidebar:
        st.header("Charger des données")
        use_sample = st.toggle("Utiliser le fichier d'exemple", value=True)
        transactions: list[dict] = []

        if use_sample:
            transactions = load_transactions(str(SAMPLE_CSV))
            st.success(f"{len(transactions)} transactions (exemple)")
        else:
            uploaded = st.file_uploader("Importer un CSV", type=["csv"])
            if uploaded:
                tmp = Path(".streamlit_upload.csv")
                tmp.write_bytes(uploaded.getvalue())
                transactions = load_transactions(str(tmp))
                tmp.unlink(missing_ok=True)
                st.success(f"{len(transactions)} transactions importées")

        st.divider()
        st.markdown(
            "**Jury :** évaluez l'ergonomie et la clarté de l'écran principal, "
            "pas seulement le score des tests."
        )

    if not transactions:
        st.info("Chargez des transactions (barre latérale) puis lancez l'analyse.")
        return

    if st.button("Analyser", type="primary"):
        try:
            st.session_state["fraud_results"] = detect_fraud(transactions)
            st.session_state["fraud_transactions"] = transactions
        except NotImplementedError:
            st.error("Implémentez d'abord `detect_fraud` dans `fraud_detection.py`.")
            return
        except Exception as exc:
            st.error(f"Erreur : {exc}")
            return

    if "fraud_results" in st.session_state:
        render_interface(
            st.session_state.get("fraud_transactions", transactions),
            st.session_state["fraud_results"],
        )


if __name__ == "__main__":
    main()
