import streamlit as st
import pandas as pd
import re
import matplotlib.pyplot as plt
import datetime as dt
import io   # <─ NEW (needed to keep the PDF in memory)


def show():
    st.title("📊 Model Analysis in Articles")

    uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls", "csv"])

    if uploaded_file:
        # Load the data
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        # Normalize status to string
        df["status"] = df["status"].fillna("").astype(str)

        articles = []
        models = []
        current_article = None

        for _, row in df.iterrows():
            status_norm = str(row.get("status", "")).strip().lower()
            data_val = str(row.get("data", "")).strip()

            if status_norm == "title":
                current_article = data_val
                articles.append({"article": current_article, "models": []})
            elif current_article and data_val:
                # --- normalize "Framework - something" → "Framework"
                if data_val.lower().startswith("framework -"):
                    data_val = "Framework"

                # treat 'yes/sim/y' as used=True; everything else as False
                used_flag = status_norm in {"yes", "sim", "y"}
                models.append({
                    "article": current_article,
                    "model": data_val,
                    "used": bool(used_flag)
                })
                articles[-1]["models"].append(data_val)

        # Ensure columns exist even if models list is empty
        models_df = pd.DataFrame(models, columns=["article", "model", "used"])
        models_df = models_df[
            models_df["model"].str.lower().str.strip() != "not valid csv text"
        ].copy()

        # Cited and used models
        cited = (
            models_df.loc[models_df["used"] == False, "model"]
            .value_counts()
            .rename_axis("Model")
            .reset_index(name="Citations")
        )

        used = (
            models_df.loc[models_df["used"] == True, "model"]
            .value_counts()
            .rename_axis("Model")
            .reset_index(name="Uses")
        )

        # Articles with no models
        articles_without_models = [a["article"] for a in articles if len(a["models"]) == 0]
        articles_without_models_df = pd.DataFrame(articles_without_models, columns=["Articles Without Models"])
        num_articles_without_models = len(articles_without_models)

        # --- Display results ---
        st.subheader("📑 Cited Models")
        st.dataframe(cited)
        st.download_button("Download Cited Models CSV",
                           cited.to_csv(index=False).encode("utf-8"),
                           "cited_models.csv",
                           "text/csv")

        st.subheader("📑 Used Models")
        st.dataframe(used)
        st.download_button("Download Used Models CSV",
                           used.to_csv(index=False).encode("utf-8"),
                           "used_models.csv",
                           "text/csv")

        st.subheader("📑 Articles Without Models")
        st.dataframe(articles_without_models_df)
        st.download_button("Download Articles Without Models CSV",
                           articles_without_models_df.to_csv(index=False).encode("utf-8"),
                           "articles_without_models.csv",
                           "text/csv")

        # ─────────────────────── 1. BAR CHART: cited ≥ 5 ───────────────────────
        st.subheader("📊 Cited Models (bar chart - cited ≥5)")
        try:
            if not models_df.empty:
                cited_count = (~models_df["used"]).groupby(models_df["model"]).sum().sort_values(ascending=False)

                top_cited = cited_count[cited_count >= 5]
                other_cited = cited_count[cited_count < 5].sum()

                if other_cited > 0:
                    top_cited["Other models"] = other_cited
                if num_articles_without_models > 0:
                    top_cited["Articles without models"] = num_articles_without_models

                fig_c, ax_c = plt.subplots(figsize=(8, 5))
                bars_c = ax_c.bar(top_cited.index, top_cited.values)

                for bar in bars_c:
                    yval = bar.get_height()
                    ax_c.text(bar.get_x() + bar.get_width() / 2, yval + 0.1,
                              int(yval), ha='center', va='bottom')

                ax_c.set_ylabel("Citation Count")
                ax_c.set_xlabel("Model")
                ax_c.set_title("Cited Models (grouping <5 as 'Other')")
                plt.xticks(rotation=45, ha="right")
                st.pyplot(fig_c)

                # download button
                buf_c = io.BytesIO()
                fig_c.savefig(buf_c, format="pdf", bbox_inches="tight")
                st.download_button("Download chart as PDF",
                                   buf_c.getvalue(),
                                   "cited_models_bar_chart.pdf",
                                   "application/pdf",
                                   key="pdf_cited_bar")
                plt.close(fig_c)
        except Exception:
            st.error("not valid csv text")


        # ─────────────────────── 3. BAR CHART: last 5 years ────────────────────
        st.subheader("📊 Cited Models in the Last 5 Years")

        def extract_year(title: str):
            m = re.search(r"(19|20)\d{2}", str(title))
            return int(m.group()) if m else None

        models_df["year"] = models_df["article"].apply(extract_year)

        current_year = dt.datetime.now().year
        last_five_years_range = list(range(current_year - 4, current_year + 1))

        recent_citations = models_df[
            (models_df["year"].isin(last_five_years_range)) &
            (~models_df["used"])
        ]

        recent_counts = (recent_citations["model"]
                         .value_counts()
                         .sort_values(ascending=False))

        if recent_counts.empty:
            st.info("No cited models found in the last 5 years.")
        else:
            fig_recent, ax_recent = plt.subplots(figsize=(8, 5))
            bars_r = ax_recent.bar(recent_counts.index, recent_counts.values,
                                   color="#48A6F2")

            for bar in bars_r:
                yval = bar.get_height()
                ax_recent.text(bar.get_x() + bar.get_width() / 2, yval + 0.1,
                               int(yval), ha="center", va="bottom")

            ax_recent.set_ylabel("Citation Count (last 5 yrs)")
            ax_recent.set_xlabel("Model")
            ax_recent.set_title(f"Cited Models ({last_five_years_range[0]}–{last_five_years_range[-1]})")
            ax_recent.set_xticklabels(recent_counts.index, rotation=90, ha="center")
            st.pyplot(fig_recent)

            buf_r = io.BytesIO()
            fig_recent.savefig(buf_r, format="pdf", bbox_inches="tight")
            st.download_button("Download chart as PDF",
                               buf_r.getvalue(),
                               "cited_models_last_5_years.pdf",
                               "application/pdf",
                               key="pdf_last5")
            plt.close(fig_recent)

            recent_counts_df = (recent_counts.rename_axis("Model")
                                .reset_index(name="Citations (last 5 yrs)"))
            st.download_button("Download Last-5-Years Citation CSV",
                               recent_counts_df.to_csv(index=False).encode("utf-8"),
                               "cited_models_last_5_years.csv",
                               "text/csv")

        # ─────────────────────── 4. LINE CHART: top models ─────────────────────
        summary = models_df.groupby("model").agg(
            citations=("used", lambda x: (~x).sum()),
            uses=("used", "sum")
        ).reset_index()

        st.subheader("📋 Summary Table: Citations and Uses")
        st.dataframe(summary)
        st.download_button("Download Summary Table CSV",
                           summary.to_csv(index=False).encode("utf-8"),
                           "summary_table.csv",
                           "text/csv")

        top_models = summary[summary["citations"] >= 5]

        plt.figure(figsize=(10, 6))
        plt.plot(top_models["model"], top_models["citations"],
                 marker="o", label="Citations")
        plt.plot(top_models["model"], top_models["uses"],
                 marker="o", label="Uses")
        plt.title("Models with ≥5 Citations: Citations vs Uses")
        plt.xlabel("Model")
        plt.ylabel("Quantity")
        plt.xticks(rotation=45, ha="right")
        plt.legend()
        st.pyplot(plt.gcf())

        buf_top = io.BytesIO()
        plt.gcf().savefig(buf_top, format="pdf", bbox_inches="tight")
        st.download_button("Download chart as PDF",
                           buf_top.getvalue(),
                           "top_models_citations_uses.pdf",
                           "application/pdf",
                           key="pdf_top10")
        plt.close()

        # ───────── 5. LINE CHART: yearly trend (>10 citations) ──────────
        st.subheader("📈 Evolution over the years – models cited more than 10 times")

        if "year" not in models_df.columns:
            models_df["year"] = models_df["article"].apply(extract_year)

        cited_only = models_df[(~models_df["used"]) & (models_df["year"].notna())].copy()

        total_citations = (cited_only.groupby("model")["model"]
                           .count()
                           .rename("total_citations"))

        popular_models = total_citations[total_citations > 10].index.tolist()

        if not popular_models:
            st.info("No model has more than 10 citations in the dataset.")
        else:
            yearly_counts = (cited_only[cited_only["model"].isin(popular_models)]
                             .groupby(["year", "model"])["model"]
                             .count()
                             .unstack(fill_value=0)
                             .sort_index())

            fig_yearly, ax_yearly = plt.subplots(figsize=(10, 6))

            for col in yearly_counts.columns:
                ax_yearly.plot(yearly_counts.index, yearly_counts[col],
                               marker="o", label=col)

            ax_yearly.set_xlabel("Year")
            ax_yearly.set_ylabel("Number of Citations")
            ax_yearly.set_title("Models cited more than 10 times – yearly trend")
            ax_yearly.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
            ax_yearly.grid(axis='y', linestyle=":", alpha=0.5)

            st.pyplot(fig_yearly)

            buf_yearly = io.BytesIO()
            fig_yearly.savefig(buf_yearly, format="pdf", bbox_inches="tight")
            st.download_button("Download chart as PDF",
                               buf_yearly.getvalue(),
                               "yearly_trend_citations.pdf",
                               "application/pdf",
                               key="pdf_yearly_trend")
            plt.close(fig_yearly)

            yearly_counts_reset = (yearly_counts.reset_index()
                                   .rename(columns={"year": "Year"}))
            st.download_button("Download yearly citation counts (models >10)",
                               yearly_counts_reset.to_csv(index=False).encode("utf-8"),
                               "yearly_citation_counts_popular_models.csv",
                               "text/csv")

            # ───── 6. LINE CHART: yearly uses (>10 uses) ─────
            used_only = models_df[(models_df["used"]) & (models_df["year"].notna())].copy()

            total_uses = (used_only.groupby("model")["model"]
                          .count()
                          .rename("total_uses"))

            popular_used_models = total_uses[total_uses > 10].index.tolist()

            if not popular_used_models:
                st.info("No model has more than 10 recorded uses in the dataset.")
            else:
                yearly_uses = (used_only[used_only["model"].isin(popular_used_models)]
                               .groupby(["year", "model"])["model"]
                               .count()
                               .unstack(fill_value=0)
                               .sort_index())

                fig_used_yearly, ax_used_yearly = plt.subplots(figsize=(10, 6))

                for model in yearly_uses.columns:
                    ax_used_yearly.plot(yearly_uses.index, yearly_uses[model],
                                        marker="o", label=model)

                ax_used_yearly.set_xlabel("Year")
                ax_used_yearly.set_ylabel("Number of Uses")
                ax_used_yearly.set_title("Models used more than 10 times – yearly trend")
                ax_used_yearly.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
                ax_used_yearly.grid(axis="y", linestyle=":", alpha=0.5)

                st.pyplot(fig_used_yearly)

                buf_used = io.BytesIO()
                fig_used_yearly.savefig(buf_used, format="pdf", bbox_inches="tight")
                st.download_button("Download chart as PDF",
                                   buf_used.getvalue(),
                                   "yearly_trend_uses.pdf",
                                   "application/pdf",
                                   key="pdf_yearly_uses")
                plt.close(fig_used_yearly)

                yearly_uses_reset = (yearly_uses.reset_index()
                                     .rename(columns={"year": "Year"}))
                st.download_button("Download yearly use counts (models >10)",
                                   yearly_uses_reset.to_csv(index=False).encode("utf-8"),
                                   "yearly_use_counts_popular_models.csv",
                                   "text/csv")

            # ───── 7. LINE CHART: total appearances per model ─────
            st.subheader("📈 Year-by-year total appearances (cited + used) per model")

            year_valid_df = models_df[models_df["year"].notna()].copy()

            if year_valid_df.empty:
                st.info("No rows with a recognisable year – cannot build the chart.")
            else:
                yearly_totals = (year_valid_df
                                 .groupby(["year", "model"])["model"]
                                 .count()
                                 .unstack(fill_value=0)
                                 .sort_index())

                popularity_threshold = 20
                popular_cols = (yearly_totals.sum()
                                .loc[lambda s: s > popularity_threshold]
                                .index)
                yearly_totals_plot = (yearly_totals[popular_cols]
                                      if len(popular_cols) else yearly_totals)

                fig_tot, ax_tot = plt.subplots(figsize=(10, 6))
                for model in yearly_totals_plot.columns:
                    ax_tot.plot(yearly_totals_plot.index, yearly_totals_plot[model],
                                marker="o", label=model)

                ax_tot.set_xlabel("Year")
                ax_tot.set_ylabel("Number of Appearances (cited + used)")
                ax_tot.set_title("Total appearances per model over the years")
                ax_tot.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
                ax_tot.grid(axis="y", linestyle=":", alpha=0.5)

                st.pyplot(fig_tot)

                buf_tot = io.BytesIO()
                fig_tot.savefig(buf_tot, format="pdf", bbox_inches="tight")
                st.download_button("Download chart as PDF",
                                   buf_tot.getvalue(),
                                   "yearly_total_appearances.pdf",
                                   "application/pdf",
                                   key="pdf_total_appearances")
                plt.close(fig_tot)

                yearly_totals_reset = (yearly_totals_plot.reset_index()
                                       .rename(columns={"year": "Year"}))
                st.download_button("Download yearly totals per model (CSV)",
                                   yearly_totals_reset.to_csv(index=False).encode("utf-8"),
                                   "yearly_totals_per_model.csv",
                                   "text/csv")

        # (the rest of your tables / lists section is unchanged)
        st.subheader("🔍  Article lists for selected models")

        target_models = {
            "BSC": ["Balanced Scorecard (BSC)"],
            "Performance Pyramid": ["SMART System / Performance Pyramid"],
            "Frameworks": ["Framework"],
            "BPMM": ["BPMM"],
            "SCOR": ["SCOR"],
            "Matrix": ["Matrix"]
        }

        def article_table(model_key, variants):
            mask = models_df["model"].str.lower().isin([v.lower() for v in variants])
            table = (models_df.loc[mask, ["article", "model", "used"]]
                     .rename(columns={"used": "Used"})
                     .drop_duplicates()
                     .sort_values("article"))
            return table

        for nice_name, spellings in target_models.items():
            tbl = article_table(nice_name, spellings)

            st.markdown(f"#### 📑 Articles that cite or use **{nice_name}**")
            if tbl.empty:
                st.info(f"No article cites or uses **{nice_name}**.")
            else:
                st.dataframe(tbl, hide_index=True, width="stretch")
                st.download_button(f"Download {nice_name} article list",
                                   tbl.to_csv(index=False).encode("utf-8"),
                                   f"articles_{nice_name.lower()}.csv",
                                   "text/csv",
                                   key=f"dl_{nice_name}")

        # --- Specific model lists ---
        only_used = summary[(summary["citations"] == 0) & (summary["uses"] > 0)]
        st.subheader("📋 Models Only Used (Not Cited)")
        if not only_used.empty:
            st.dataframe(only_used)
            st.download_button("Download Only Used Models CSV",
                               only_used.to_csv(index=False).encode("utf-8"),
                               "only_used_models.csv",
                               "text/csv")
        else:
            st.info("No models are used but not cited.")

        only_cited = summary[(summary["citations"] > 0) & (summary["uses"] == 0)]
        st.subheader("📋 Models Only Cited (Not Used)")
        if not only_cited.empty:
            st.dataframe(only_cited)
            st.download_button("Download Only Cited Models CSV",
                               only_cited.to_csv(index=False).encode("utf-8"),
                               "only_cited_models.csv",
                               "text/csv")
        else:
            st.info("No models are cited but not used.")

        used_more_than_cited = summary[summary["uses"] > summary["citations"]]
        st.subheader("📋 Models Used More Than Cited")
        if not used_more_than_cited.empty:
            st.dataframe(used_more_than_cited)
            st.download_button("Download Models Used More Than Cited CSV",
                               used_more_than_cited.to_csv(index=False).encode("utf-8"),
                               "used_more_than_cited.csv",
                               "text/csv")
        else:
            st.info("No models are used more than cited.")

        cited_more_than_used = summary[summary["citations"] > summary["uses"]]
        st.subheader("📋 Models Cited More Than Used")
        if not cited_more_than_used.empty:
            st.dataframe(cited_more_than_used)
            st.download_button("Download Models Cited More Than Used CSV",
                               cited_more_than_used.to_csv(index=False).encode("utf-8"),
                               "cited_more_than_used.csv",
                               "text/csv")
        else:
            st.info("No models are cited more than used.")
