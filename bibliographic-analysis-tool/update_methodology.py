with open('c:\\Users\\pedro\\Videos\\save_TCC\\bibliographic-analysis-tool\\access.txt', 'r', encoding='utf8') as f:
    content = f.read()

start_str = r'To reconcile geometric density assignments from HDBSCAN with probabilistic clusters from GSDMM'
end_str = r'stratifying topics into motor themes'

s1 = content.find(start_str)
s2 = content.find(end_str)

if s1 != -1 and s2 != -1:
    new_thematic = r'''To reconcile the dense spatial embeddings from BERTopic with the probabilistic lexical micro-clusters from GSDMM, the platform implements a \textbf{Consensus-First Many-to-One Alignment Engine}. Rather than isolating models, the system maps every GSDMM cluster to its closest BERTopic leader pillar using a hybrid similarity metric ($60\%$ document co-occurrence Jaccard $+ 40\%$ keyword vocabulary overlap).

The pipeline executes a \textbf{Two-Pass Iterative Refinement}:
\begin{enumerate}
    \item \textbf{Pass 1 (Consensus Core Identification):} Documents where both BERTopic and GSDMM agree receive a strict consensus flag and $100\%$ confidence. These pure consensus cores calculate high-purity topic centroids in the embedding space ($\mathbf{c}_k = \frac{\sum_{i \in \text{Core}_k} \mathbf{e}_i}{\|\sum_{i \in \text{Core}_k} \mathbf{e}_i\|}$).
    \item \textbf{Pass 2 (Centroid Boundary Resolution):} Boundary and divergent documents are projected against all topic centroids via cosine similarity. If a document aligns strongly with an alternative topic's centroid, it is decisively reassigned with calibrated confidence. 
\end{enumerate}
This architecture completely eliminates empty "ghost topics" and guarantees robust, well-populated macro-thematic pillars. Finally, topics are mapped onto a strategic Callon Diagram \cite{callon1983word, cobo2011approach, cobo2012scimat}, positioning clusters along density and centrality coordinates derived from the co-word equivalence index $e_{ij}$:
\begin{equation}
\label{eq:callon_metrics}
e_{ij} = \frac{(c_{ij})^2}{c_i \times c_j}, \quad C_k = 10 \sum_{i \in k, j \notin k} e_{ij}, \quad D_k = \frac{100}{N_k} \sum_{i,j \in k} e_{ij}
\end{equation}
stratifying topics into motor themes'''

    new_content = content[:s1] + new_thematic + content[s2 + len(end_str):]
    with open('c:\\Users\\pedro\\Videos\\save_TCC\\bibliographic-analysis-tool\\access.txt', 'w', encoding='utf8') as f:
        f.write(new_content)
    print('Thematic updated successfully.')
else:
    print('Failed to find boundaries')
