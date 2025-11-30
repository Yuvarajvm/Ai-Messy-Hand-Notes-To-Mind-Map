# services/llm_post.py
import os
import logging
import google.generativeai as genai
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("✅ Gemini API configured")

def llm_clean_and_structure(text: str, summary_level: str = "normal") -> Dict[str, Any]:
    """
    Use Gemini to clean, summarize, and extract structure from text
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""You are analyzing educational/technical notes. Please process this text and provide:

1. CLEANED TEXT: Rewrite the text with proper formatting, fixing OCR errors, and organizing into clear paragraphs
2. SUMMARY: A concise {summary_level} summary (2-3 sentences)
3. KEY CONCEPTS: Extract 10-15 main concepts/topics (just the concept names, comma-separated)
4. RELATIONSHIPS: Identify 5-10 relationships between concepts in format "Concept A -> relates to -> Concept B"

TEXT TO ANALYZE:
{text[:15000]}

Respond in this exact format:
CLEANED_TEXT:
[your cleaned text here]

SUMMARY:
[your summary here]

KEY_CONCEPTS:
[concept1, concept2, concept3, ...]

RELATIONSHIPS:
[Concept A -> Concept B]
[Concept C -> Concept D]
..."""

        response = model.generate_content(prompt)
        result_text = response.text
        
        # Parse the response
        sections = {
            "clean_text": "",
            "summary": "",
            "key_concepts": [],
            "relationships": []
        }
        
        current_section = None
        lines = result_text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('CLEANED_TEXT:'):
                current_section = 'clean_text'
                continue
            elif line.startswith('SUMMARY:'):
                current_section = 'summary'
                continue
            elif line.startswith('KEY_CONCEPTS:'):
                current_section = 'key_concepts'
                continue
            elif line.startswith('RELATIONSHIPS:'):
                current_section = 'relationships'
                continue
            
            if not line:
                continue
                
            if current_section == 'clean_text':
                sections['clean_text'] += line + '\n'
            elif current_section == 'summary':
                sections['summary'] += line + ' '
            elif current_section == 'key_concepts':
                # Parse comma-separated concepts
                concepts = [c.strip() for c in line.split(',')]
                sections['key_concepts'].extend([c for c in concepts if c])
            elif current_section == 'relationships':
                # Parse relationships
                if '->' in line:
                    sections['relationships'].append(line)
        
        # Clean up
        sections['clean_text'] = sections['clean_text'].strip()
        sections['summary'] = sections['summary'].strip()
        
        logger.info(f"Gemini extracted {len(sections['key_concepts'])} concepts and {len(sections['relationships'])} relationships")
        
        return {
            "clean_text": sections['clean_text'] or text[:5000],
            "summary": sections['summary'] or "Text processed successfully.",
            "bullet_points": sections['key_concepts'],
            "relations": sections['relationships']
        }
        
    except Exception as e:
        logger.error(f"Gemini processing failed: {e}")
        return {
            "clean_text": text[:5000],
            "summary": "Text extracted successfully.",
            "bullet_points": [],
            "relations": []
        }


def extract_mindmap_with_gemini(text: str, max_concepts: int = 12) -> Dict[str, Any]:
    """
    Use Gemini to directly generate a mindmap structure
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""Analyze this educational/technical content and create a hierarchical mindmap.

TEXT:
{text[:15000]}

Generate a mindmap with:
- 1 CENTRAL topic (the main subject)
- 4-6 MAIN branches (major subtopics)
- 2-3 SUB-branches under each main branch (specific details)

Respond in this format:
CENTRAL: [main topic]
BRANCH: [branch name]
  SUB: [sub-topic]
  SUB: [sub-topic]
BRANCH: [branch name]
  SUB: [sub-topic]
  SUB: [sub-topic]
..."""

        response = model.generate_content(prompt)
        result_text = response.text
        
        # Parse mindmap structure
        central = None
        branches = []
        current_branch = None
        
        for line in result_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('CENTRAL:'):
                central = line.replace('CENTRAL:', '').strip()
            elif line.startswith('BRANCH:'):
                if current_branch:
                    branches.append(current_branch)
                current_branch = {
                    'name': line.replace('BRANCH:', '').strip(),
                    'subs': []
                }
            elif line.startswith('SUB:') and current_branch:
                sub = line.replace('SUB:', '').strip()
                current_branch['subs'].append(sub)
        
        if current_branch:
            branches.append(current_branch)
        
        # If parsing failed, return empty
        if not central:
            return None
            
        return {
            'central': central,
            'branches': branches
        }
        
    except Exception as e:
        logger.error(f"Gemini mindmap generation failed: {e}")
        return None
