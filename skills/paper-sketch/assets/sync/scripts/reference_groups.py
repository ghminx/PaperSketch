
"""검색 그룹 준비·실행에서 공유하는 원본 후보 표현과 예산."""
import time
import threading
GROUP_CHAR_BUDGET = 800000
PER_GROUP = 6

def candidate_text(index: int, row: dict) -> str:
    """원본 Retriever 형식의 전체 후보 블록 구성."""
    return f"Candidate Diagram {index}:\n- Diagram ID: {row['id']}\n- Caption: {row['visual_intent']}\n- Methodology section: {str(row['content'])}\n\n"
