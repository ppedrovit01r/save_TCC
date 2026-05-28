# bibliographic-analysis-tool

Este repositório contém os artefatos de pesquisa desenvolvidos no âmbito do BPM Research Lab – UFRGS.

## 🇧🇷 Português

## 📌 Contexto de Pesquisa

Esse repositório possui um projeto de pesquisa academico conluido desenvolvido no **BPM Research Lab da Universidade Federal do Rio Grande do Sul (UFRGS).**
- Pesquisadora: Leticia Naomi Asano
- Orientadora: Profa. Dra. Lucineia Heloisa Thom
- Laboratório: BPM Research Lab – UFRGS

A pesquisa investiga indicadores de performance através de uma análise bibliométrica. Para realizar a análise, o código presente nesse repositório foi desenvolvido, incluindo as ferramentas de extração de dados, análise de performance e science maping.

## 📋 Visão Geral
Este repositório contém 3 pastas principais. Em biliographic_analysis_on_indicators, o código foi adaptado especialmente para a pesquisa em indicadores e não pode ser reaporveitado. Em articles, temos os artigos que foram usados na pesquisa. Finalmente em biliographic_analysis_tool disponibilizamos a aplicação de análise bibliometrica em versão genérica, que pode ser reaproveitada por outros pesquisadores para realizar análise bibliométrica.

## 📂 Directory Structure

```text
bibliographic-analysis-tool/
├── articles/           # Contains the articles used during the research on the performance indicators
│
├── biliographic_analysis_on_indicators/
│   └── analysis
|           └── performance_analysis.py     # File with the code that runs performance analysis. Here we can upload the TestSet.xlsx file to see graphics.
|           └── science_mapping.py          # File with the code that runs science mapping. Here we can upload the TestSet.xlsx file to see graphics.
│   └── architecture
|           └── architecture.png
|           └── architecture.puml
│   └── data
|           └── .DS_Store
|           └── data_preparation.py          # File that extracts metadata using crossref API
│   └── lib/                                 # Content is the same as the lib specified bellow
│   └── TestSet.xlsx                         # Contains test data to see the graphics
│   └── .DS_Store
│   └── app.py                               # App that runs the Streamlit file
│   └── requirementes.txt    
│
├── biliographic_analysis_on_indicators/
│   └── analysis
|           └── performance_analysis.py     # File with the code that runs performance analysis. Here we can upload the allMetadata.xlsx file to see graphics.
|           └── qualitative_analysis.py     # File with the code that runs qualitative analysis. Here we can upload the modelsFiltered.xlsx file to see graphics.
|           └── science_mapping.py          # File with the code that runs science mapping. Here we can upload the allMetadata.xlsx file to see graphics.
│   └── architecture
|           └── architecture.png
|           └── architecture.puml
│   └── data
|           └── .DS_Store
|           └── data_preparation.py          # File that extracts metadata using crossref API
│   └── data_samples
|           └── .DS_Store
|           └── allMetadata.xlsx             # Contains the metadata that was used to produce the research
|           └── modelsFiltered.xlsx          # Contains the models on performace indicators extracted by the LLM          
│   └── lib/                                 # Content is the same as the lib specified bellow
│   └── modelos/
|           └── .DS_Store
|           └── get_models.py                #Contains the code used for extracting text from the articles using LLM
│   └── .DS_Store
│   └── app.py                               # App that runs the Streamlit file
│   └── requirementes.txt    
│
├── lib/                                     # Configuration files for used libraries
|    └── bindings
|           └── utils.js
|    └── tom-select
|           └── tom-select.complete.min.js
|           └── tom-select.css
|    └── vis-9.1.2
|           └── vis-network.css
|           └── vis-network.min.js
|
├── .DS_Store
├── README.md
└── LICENSE
```

##  🚀 Instalação Local: bibliographic-analysis-tool
1 - Para rodar a aplicação é necessário Python 3 ou superior
2 - Instalar Streamlit e as dependencias
```text
pip install -r requirements.txt
```
3 - Clonar a pasta bibliographic-analysis-tool
4 - Abrir o terminal onde a pasta foi clonada e rodar o streamlit, usando o path absoluto do arquivo app.py do seu computador:
```text
python3 -m streamlit run localnoseucomputador/bibliographic-analysis-tool/app.py
```
5 - O link deve abrir automaticamente no broweser. Alternativamente, acessar o endereço **http://localhost:8501/**

## 🚀 Instalação Local: biliographic_analysis_on_indicators
O processo de instalação é idêntico, a única diferença é o repositório clonado: **biliographic_analysis_on_indicators**  

## ⚙️ Como executar
### Aba **Data Preparation**
 - É necessário ter um excel com dados de citações a serem completos através da crossref api. 
 - Para ter extrair o DOI, as citações precisam ter título. Para extrair outros dados, precisam de DOI
 - Atualmente, os dados que podem ser extraídos são: DOI, Title, Author, Publication Year, Article References, Times Cited, Publisher, Abstract, Language.
 - Para extrair os dados, o excel deve ter uma coluna com o nome do dado a ser extraído, que deve ser exatamente igual aos citados anteriormente, em qualquer ordem.
 - ATENÇÃO: a extração leva bastante tempo, principalmente se os dados forem numerosos.

### Aba **Performance Analysis**
- É necessário ter um excel com dados de citação a serem analisados
- Os dados obrigatórios são: Title, Publication Year, Times Cited, DOI, Author
- As colunas contendo esses dados devem ter exatemente esses títulos
- Para teste é possível usar os arquivos disponibilizados: TestSet.xlsx ou allMetadata.xlsx que contém os dados usados na pesquisa de indicadores
- Após fazer o upload do Excel, basta visualizar os dados

### Aba **Science Mapping**
- É necessário ter um excel com dados de citação a serem analisados
- Os dados obrigatórios são: Title, DOI, Author, Article References
- As colunas contendo esses dados devem ter exatemente esses títulos
- Para teste é possível usar os arquivos disponibilizados: TestSet.xlsx ou allMetadata.xlsx que contém os dados usados na pesquisa de indicadores
- Após fazer o upload do Excel, basta visualizar os dados

### Aba **Qualitative Analysis** (apenas a pasta biliographic_analysis_on_indicators)
Essa aba é restrita aos dados da pesquisa de indicadores de performance.
Para visualizar os dados, basta fazer o upload do arquivo modelsFiltered.xlsx


## ⚖️ Dados e Ética
Este projeto segue as diretrizes do laboratório:

Scripts e datasets destinados exclusivamente para uso educacional e de pesquisa.
Redistribuição ou uso comercial não permitidos sem autorização prévia.
Ao utilizar este código, cite o BPM Research Lab – UFRGS.


## 🇺🇸 English

## 📌 Research Context

This repository contains an ongoing academic research project developed at the BPM Research Lab of the Federal University of Rio Grande do Sul (UFRGS).
- Researcger: Leticia Naomi Asano
- Supervisor: Profa. Dra. Lucineia Heloisa Thom
- Lab: BBPM Research Lab – UFRGS

This research investigates performance inidcators using a bibliometric analysis. To perform this analysis, the code of this repository was developed, including tools to extract the data, analyse the performance and science mapping.

## 📋 Overview
This repository has 3 main folders. In biliographic_analysis_on_indicators, the code has been developed specialy for the indicator research and is not meant for general use. In articles, we have the articles that were used on the research. Finally, in biliographic_analysis_tool the application of bibliometric analysis is available in the general version, and can be reused by other researchers to perform bibliometric analysis.

## 📂 Directory Structure

```text
bibliographic-analysis-tool/
├── articles/           # Contains the articles used during the research on the performance indicators
│
├── biliographic_analysis_on_indicators/
│   └── analysis
|           └── performance_analysis.py     # File with the code that runs performance analysis. Here we can upload the TestSet.xlsx file to see graphics.
|           └── science_mapping.py          # File with the code that runs science mapping. Here we can upload the TestSet.xlsx file to see graphics.
│   └── architecture
|           └── architecture.png
|           └── architecture.puml
│   └── data
|           └── .DS_Store
|           └── data_preparation.py          # File that extracts metadata using crossref API
│   └── lib/                                 # Content is the same as the lib specified bellow
│   └── TestSet.xlsx                         # Contains test data to see the graphics
│   └── .DS_Store
│   └── app.py                               # App that runs the Streamlit file
│   └── requirementes.txt    
│
├── biliographic_analysis_on_indicators/
│   └── analysis
|           └── performance_analysis.py     # File with the code that runs performance analysis. Here we can upload the allMetadata.xlsx file to see graphics.
|           └── qualitative_analysis.py     # File with the code that runs qualitative analysis. Here we can upload the modelsFiltered.xlsx file to see graphics.
|           └── science_mapping.py          # File with the code that runs science mapping. Here we can upload the allMetadata.xlsx file to see graphics.
│   └── architecture
|           └── architecture.png
|           └── architecture.puml
│   └── data
|           └── .DS_Store
|           └── data_preparation.py          # File that extracts metadata using crossref API
│   └── data_samples
|           └── .DS_Store
|           └── allMetadata.xlsx             # Contains the metadata that was used to produce the research
|           └── modelsFiltered.xlsx          # Contains the models on performace indicators extracted by the LLM          
│   └── lib/                                 # Content is the same as the lib specified bellow
│   └── modelos/
|           └── .DS_Store
|           └── get_models.py                #Contains the code used for extracting text from the articles using LLM
│   └── .DS_Store
│   └── app.py                               # App that runs the Streamlit file
│   └── requirementes.txt    
│
├── lib/                                     # Configuration files for used libraries
|    └── bindings
|           └── utils.js
|    └── tom-select
|           └── tom-select.complete.min.js
|           └── tom-select.css
|    └── vis-9.1.2
|           └── vis-network.css
|           └── vis-network.min.js
|
├── .DS_Store
├── README.md
└── LICENSE
```

##  🚀 Locan installing: bibliographic-analysis-tool
1 - To run the application python 3 or superior is needed
2 - Install Streamlit and dependencies
```text
pip install -r requirements.txt
```
3 - Clone bibliographic-analysis-tool
4 -Open the folder where the repository was cloned and run streamlit with the absolute path of app.py in your computer
```text
python3 -m streamlit run folderinyourcomputer/bibliographic-analysis-tool/app.py
```
5 -The link should automatically open your default browser. Alternatively, access the address **http://localhost:8501/**

## 🚀 Local installation: biliographic_analysis_on_indicators
The process of installation is identical to the formar, except for the folder that must be cloned: **biliographic_analysis_on_indicators**  

## ⚙️ How to execute 
### Tab **Data Preparation**
- An Excel is needed with citation data to be completed using crossref api
- To extract DOI, citations must have title. To extract other data, citation must hav DOI
- The data that can be extracted are: DOI, Title, Author, Publication Year, Article References, Times Cited, Publisher, Abstract, Language.
- To extract the data, excel must have a column with the name of the data that should be extracted. The name has to exactly matched the names cited before, in any order.
- ATENTION: the extraction takes a long time, specially if there is to much data

### Tab **Performance Analysis**
- An excel with the citation data to be analysed is required
- The mandatory data are: Title, Publication Year, Times Cited, DOI, Author
- The columns with these data must have exactly these titles
- For testing, the sample data here can be used: TestSet.xlsx or allMetadata.xlsx (containing data used on the performance indicator research)
- After making the Excel upload, the data should be available for visualization

### Tab **Science Mapping**
-  An excel with the citation data to be analysed is required
- The mandatory data are: itle, DOI, Author, Article References
- The columns with these data must have exactly these titles
- For testing, the sample data here can be used: TestSet.xlsx or allMetadata.xlsx (containing data used on the performance indicator research)
- After making the Excel upload, the data should be available for visualization

### Tab **Qualitative Analysis** (apenas a pasta biliographic_analysis_on_indicators)
This tab is restricted to data of the performance indicator reserach. To visualize the data, upload the file modelsFiltered.xlsx.


⚖️ License and Responsibility
All scripts and datasets are intended exclusively for educational and research use. Redistribution, commercial use, or derivative works are not allowed without prior authorization.

If you use this code or its outputs, please cite or acknowledge the BPM Research Lab – UFRGS.

Contact: Guilherme Rego Rockembach
Instagram: @bpm_research_lab_ufrgs





