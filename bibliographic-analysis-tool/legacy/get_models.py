
from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
from gen_ai_hub.proxy.core.proxy_clients import get_proxy_client
from gen_ai_hub.proxy.native.openai import completions
import PyPDF2
import os, io, csv
import pandas as pd
from io import StringIO
import tiktoken




proxy_client = get_proxy_client('gen-ai-hub')


llm = ChatOpenAI(
        proxy_model_name='o3',
        temperature=0.1,
        proxy_client=proxy_client
) 
def extract_text_from_pdf(pdf_path):
    text = ''
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return text

def pdf_loop(pdf_folder, csv_path, error_path):
    verifier = 0
    pdf_files = [f for f in os.listdir(pdf_folder) if f.endswith('.pdf')]
    for file in pdf_files:
        print(verifier)
        verifier += 1
        try:
                text = extract_text_from_pdf(os.path.join(pdf_folder, file))
                response = call_llm_indicators(text, file)
        except Exception as e:
            print(f'Error processing {file}: {e}')
            error_articles(file, error_path)
            continue  
        insert_into_table(csv_path, response, file)
        
def call_llm_indicators(text, file):
    prompt  = "Retorne uma tabela csv com os modelos de indicadores de performance de processos de negócio citados no texto, informando se eles são usados para construir medidores ou apenas citados e trechos do texto que corroboram essa informação"
    final_prompt = text+"\n"+prompt
    encoding = tiktoken.get_encoding("cl100k_base")
    if(len(encoding.encode(text)) >= 200000):
         error_articles(file)
         return 
    response = llm.invoke(input=final_prompt, max_tokens=100000)
    return response.content

def insert_into_table(csv_path, response_string, label_row):
    if isinstance(label_row, str):
        label_row = next(csv.reader([label_row]))
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(label_row)  
        csv_string = extract_csv_block(label_row, response_string)
        if csv_string:               
                reader = csv.reader(io.StringIO(csv_string))
                writer.writerows(reader)      
        else:
                error_row = next(csv.reader(["Not valid csv text, check the article"]))
                writer.writerow(error_row)  

def extract_csv_block(title, text: str, delimiter: str = ",") :
    if not isinstance(text, str):
        error_articles(title)
        return None
    lines = text.splitlines()
    num_lines = len(lines)
    for start in range(num_lines):
        if delimiter not in lines[start]:
            continue
        header_row = next(csv.reader([lines[start]], delimiter=delimiter))
        width = len(header_row)
        if width < 2:
            continue  
        candidate_lines = [lines[start]]
        for i in range(start + 1, num_lines):
            line = lines[i]
            if not line.strip() or delimiter not in line:
                break
            row = next(csv.reader([line], delimiter=delimiter))
            if len(row) != width:
                break  
            candidate_lines.append(line)
        if len(candidate_lines) >= 2:
            return "\n".join(candidate_lines)
    return None

def error_articles(article, error_path):
      with open(error_path, "a", newline="", encoding="utf-8") as f:
        if isinstance(article, str):
            f.write(article)
            f.write("\n")


     


