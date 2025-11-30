# backend/services/pdf_export.py
import io
import logging
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib import colors
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)


class MindmapPDFExporter:
    """Export mindmap results to professional PDF"""
    
    def __init__(self, title="Mindmap Results", author="AI Notes Mindmap"):
        self.title = title
        self.author = author
        self.width, self.height = letter
        
    def generate_pdf(self, data: dict) -> bytes:
        """
        Generate comprehensive PDF from mindmap results
        
        Args:
            data: Dict containing text, summary, keyphrases, mindmap, meta
            
        Returns:
            PDF file as bytes
        """
        try:
            pdf_buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                pdf_buffer,
                pagesize=letter,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch,
                title=self.title,
                author=self.author,
            )
            
            # Story to hold all elements
            story = []
            styles = getSampleStyleSheet()
            
            # Custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=28,
                textColor=colors.HexColor('#5A8A7A'),
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=16,
                textColor=colors.HexColor('#3A6768'),
                spaceAfter=12,
                spaceBefore=12,
                fontName='Helvetica-Bold',
                borderColor=colors.HexColor('#5A8A7A'),
                borderWidth=2,
                borderPadding=10,
            )
            
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_JUSTIFY,
                spaceAfter=10,
                leading=14,
            )
            
            concept_style = ParagraphStyle(
                'ConceptText',
                parent=styles['Normal'],
                fontSize=10,
                alignment=TA_LEFT,
                spaceAfter=6,
                leading=12,
            )
            
            # ========== TITLE PAGE ==========
            story.append(Spacer(1, 0.5*inch))
            story.append(Paragraph("📊 AI Notes Mindmap", title_style))
            story.append(Spacer(1, 0.3*inch))
            
            # Metadata
            meta = data.get('meta', {})
            subtitle_text = f"""
            <font size=12>
            <b>Processing Report</b><br/>
            Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}<br/>
            Files Processed: {meta.get('files_success', 0)}/{meta.get('files_processed', 0)}<br/>
            Total Characters: {meta.get('total_chars', 0):,}<br/>
            Concepts Found: {meta.get('concept_count', 0)}<br/>
            </font>
            """
            story.append(Paragraph(subtitle_text, normal_style))
            story.append(Spacer(1, 0.3*inch))
            
            # Summary
            summary = data.get('summary', '')
            if summary:
                story.append(Paragraph("<b>Summary</b>", heading_style))
                story.append(Paragraph(summary, normal_style))
                story.append(Spacer(1, 0.2*inch))
            
            story.append(PageBreak())
            
            # ========== SECTION 1: KEY CONCEPTS ==========
            story.append(Paragraph("🔑 Key Concepts", heading_style))
            story.append(Spacer(1, 0.15*inch))
            
            keyphrases = data.get('keyphrases', [])
            if keyphrases:
                # Create concept table
                concept_data = [["#", "Concept", "Relevance"]]
                
                for idx, kp in enumerate(keyphrases, 1):
                    phrase = kp.get('phrase', 'Unknown')
                    score = kp.get('score', 0.5)
                    relevance_bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
                    concept_data.append([
                        str(idx),
                        phrase,
                        f"{relevance_bar} {int(score*100)}%"
                    ])
                
                concept_table = Table(concept_data, colWidths=[0.5*inch, 3*inch, 1.5*inch])
                concept_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5A8A7A')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 11),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FAF8F3')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#3A6768')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAF8F3')]),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 10),
                    ('LEFTPADDING', (0, 0), (-1, -1), 10),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ]))
                
                story.append(concept_table)
                story.append(Spacer(1, 0.3*inch))
            
            story.append(PageBreak())
            
            # ========== SECTION 2: MINDMAP STRUCTURE ==========
            story.append(Paragraph("🧠 Mindmap Structure", heading_style))
            story.append(Spacer(1, 0.15*inch))
            
            mindmap = data.get('mindmap', {})
            nodes = mindmap.get('nodes', [])
            edges = mindmap.get('edges', [])
            
            if nodes:
                # Mindmap statistics
                stats_text = f"""
                <font size=11>
                <b>Graph Statistics:</b><br/>
                • Total Nodes: {len(nodes)}<br/>
                • Total Connections: {len(edges)}<br/>
                • Network Density: {self._calculate_density(nodes, edges):.2%}<br/>
                </font>
                """
                story.append(Paragraph(stats_text, normal_style))
                story.append(Spacer(1, 0.2*inch))
                
                # Node listing
                story.append(Paragraph("<b>Nodes in Mindmap:</b>", normal_style))
                story.append(Spacer(1, 0.1*inch))
                
                node_data = [["ID", "Node Label"]]
                for node in nodes[:30]:  # Limit to first 30 nodes
                    node_data.append([
                        node.get('id', ''),
                        node.get('label', 'Unknown')[:60]
                    ])
                
                if len(nodes) > 30:
                    node_data.append(["...", f"... and {len(nodes) - 30} more nodes"])
                
                node_table = Table(node_data, colWidths=[0.8*inch, 4.5*inch])
                node_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5A8A7A')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FAF8F3')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#3A6768')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAF8F3')]),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                
                story.append(node_table)
                story.append(Spacer(1, 0.3*inch))
            
            story.append(PageBreak())
            
            # ========== SECTION 3: EXTRACTED TEXT ==========
            story.append(Paragraph("📄 Extracted Text", heading_style))
            story.append(Spacer(1, 0.15*inch))
            
            text = data.get('text', '')
            if text:
                # Limit to first 2000 chars for PDF size
                display_text = text[:2000]
                if len(text) > 2000:
                    display_text += "\n\n[... text truncated for PDF size ...]"
                
                text_style = ParagraphStyle(
                    'ExtractedText',
                    parent=styles['Normal'],
                    fontSize=10,
                    alignment=TA_JUSTIFY,
                    spaceAfter=10,
                    leading=13,
                    textColor=colors.HexColor('#2B3A3A'),
                )
                
                story.append(Paragraph(display_text, text_style))
            
            story.append(Spacer(1, 0.5*inch))
            
            # ========== FOOTER ==========
            story.append(Paragraph(
                f"<font size=9 color='#6B7B7B'>Report generated by AI Notes Mindmap • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</font>",
                ParagraphStyle('Footer', parent=styles['Normal'], alignment=TA_CENTER)
            ))
            
            # Build PDF
            doc.build(story)
            pdf_buffer.seek(0)
            
            logger.info(f"✅ PDF generated successfully ({len(pdf_buffer.getvalue())} bytes)")
            return pdf_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"❌ PDF generation failed: {e}")
            raise
    
    def _calculate_density(self, nodes, edges):
        """Calculate network density"""
        if not nodes:
            return 0
        n = len(nodes)
        max_edges = n * (n - 1) / 2
        return len(edges) / max_edges if max_edges > 0 else 0


def export_results_to_pdf(data: dict) -> bytes:
    """Helper function to export results to PDF"""
    exporter = MindmapPDFExporter(title="AI Notes Mindmap Results")
    return exporter.generate_pdf(data)
