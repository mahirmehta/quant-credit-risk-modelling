"""
IEEE Transactions Publication-Grade Word & PDF Report Compiler
Quantitative Analysis of Financial Markets - Term Research Project
Authors: Mahir Mehta, Kunj Maheshwari, Manan Chandarana, Bhumika Agrawal, Kashish Seth
Singapore Management University | Master of Science in Quantitative Finance

Workflow:
1. Parses docs/REPORT.md
2. Constructs a publication-grade Microsoft Word document (docs/REPORT.docx):
   - Strict IEEE Transactions styling: Times New Roman body, pure black typography throughout (NO COLORS).
   - Native Office Math (OMML) equations converted via Microsoft MML2OMML.XSL:
     crisp vertical fractions, radical square roots, summations, Greek symbols, and numbered equation tags.
   - Formal IEEE booktabs tables (top rule, mid header rule, bottom rule, no vertical lines, NO background fills).
   - Centered 300 DPI high-resolution research figures with formal IEEE captions referring to all results.
   - Running IEEE footers with pure black rules and page numbers.
3. Automates Microsoft Word COM to export docs/REPORT.docx directly into docs/REPORT.pdf.
"""

import os
import re
import shutil
from pathlib import Path
import lxml.etree as ET

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

import win32com.client

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
FIGURES_DIR = ROOT_DIR / "results" / "figures"
REPORT_DIR = ROOT_DIR / "report"
REPORT_MD = REPORT_DIR / "REPORT.md"
OUTPUT_DOCX = REPORT_DIR / "REPORT.docx"
OUTPUT_PDF = REPORT_DIR / "REPORT.pdf"

REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Find MML2OMML.XSL
def find_mml2omml_xsl() -> Path:
    candidates = [
        Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
        Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL"),
        Path(r"C:\Program Files\Microsoft Office\Office16\MML2OMML.XSL"),
        Path(r"C:\Program Files (x86)\Microsoft Office\Office16\MML2OMML.XSL"),
    ]
    for c in candidates:
        if c.exists():
            return c
    # Search Program Files
    for base in [r"C:\Program Files\Microsoft Office", r"C:\Program Files (x86)\Microsoft Office"]:
        if os.path.exists(base):
            for root, dirs, files in os.walk(base):
                for f in files:
                    if f.upper() == "MML2OMML.XSL":
                        return Path(root) / f
    raise FileNotFoundError("MML2OMML.XSL could not be located in Microsoft Office installation.")


# Complete MathML Library for Credit Risk Project Equations
MATHML_MAP = {
    # Eq 1: Latent credit equation
    "latent_credit": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msubsup><mi>y</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>*</mo></msubsup>
        <mo>=</mo>
        <msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mi>β</mi>
        <mo>+</mo>
        <msub><mi>Z</mi><mi>t</mi></msub><mi>γ</mi>
        <mo>+</mo>
        <msub><mi>α</mi><mi>s</mi></msub>
        <mo>+</mo>
        <msub><mi>ϵ</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub>
        <mo>,</mo><mspace width="1em"/>
        <msub><mi>ϵ</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub>
        <mo>∼</mo>
        <mi mathvariant="script">N</mi><mo>(</mo><mn>0</mn><mo>,</mo><mn>1</mn><mo>)</mo>
      </mrow>
    </math>""",

    # Eq 2: Cutpoint mapping
    "cutpoint_mapping": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>=</mo><mi>k</mi>
        <mspace width="0.5em"/>
        <mo>⟺</mo>
        <mspace width="0.5em"/>
        <msub><mi>μ</mi><mrow><mi>k</mi><mo>−</mo><mn>1</mn></mrow></msub>
        <mo>&lt;</mo>
        <msubsup><mi>y</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>*</mo></msubsup>
        <mo>≤</mo>
        <msub><mi>μ</mi><mi>k</mi></msub>
      </mrow>
    </math>""",

    # Eq 3: Ordered Probit probability
    "probit_prob": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mi>P</mi><mo>(</mo><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>=</mo><mi>k</mi><mo>∣</mo><msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>,</mo><msub><mi>Z</mi><mi>t</mi></msub><mo>)</mo>
        <mo>=</mo>
        <mi>Φ</mi><mo>(</mo><msub><mi>μ</mi><mi>k</mi></msub><mo>−</mo><msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mi>β</mi><mo>−</mo><msub><mi>Z</mi><mi>t</mi></msub><mi>γ</mi><mo>−</mo><msub><mi>α</mi><mi>s</mi></msub><mo>)</mo>
        <mo>−</mo>
        <mi>Φ</mi><mo>(</mo><msub><mi>μ</mi><mrow><mi>k</mi><mo>−</mo><mn>1</mn></mrow></msub><mo>−</mo><msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mi>β</mi><mo>−</mo><msub><mi>Z</mi><mi>t</mi></msub><mi>γ</mi><mo>−</mo><msub><mi>α</mi><mi>s</mi></msub><mo>)</mo>
      </mrow>
    </math>""",

    # Eq 4: Point-in-time latent shadow rating
    "shadow_rating": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msub><mi>S</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub>
        <mo>≡</mo>
        <munderover><mo>∑</mo><mrow><mi>k</mi><mo>=</mo><mn>1</mn></mrow><mi>K</mi></munderover>
        <mi>k</mi><mo>·</mo><mi>P</mi><mo>(</mo><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>=</mo><mi>k</mi><mo>∣</mo><msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>,</mo><msub><mi>Z</mi><mi>t</mi></msub><mo>)</mo>
        <mo>=</mo>
        <mi mathvariant="double-struck">E</mi><mo>[</mo><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>∣</mo><msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>,</mo><msub><mi>Z</mi><mi>t</mi></msub><mo>]</mo>
      </mrow>
    </math>""",

    # Eq 5: Partial adjustment mechanism
    "partial_adjustment": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mi>Δ</mi><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub>
        <mo>=</mo>
        <msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>−</mo><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi><mo>−</mo><mn>1</mn></mrow></msub>
        <mo>=</mo>
        <mi>λ</mi><mo>(</mo><msub><mi>S</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>−</mo><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi><mo>−</mo><mn>1</mn></mrow></msub><mo>)</mo>
        <mo>+</mo>
        <msub><mi>u</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub>
      </mrow>
    </math>""",

    # Eq 6: Rating adjustment half-life
    "rating_half_life": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msub><mi>t</mi><mrow><mn>1</mn><mo>/</mo><mn>2</mn></mrow></msub>
        <mo>=</mo>
        <mfrac>
          <mrow><mi>ln</mi><mo>(</mo><mn>0.5</mn><mo>)</mo></mrow>
          <mrow><mi>ln</mi><mo>(</mo><mn>1</mn><mo>−</mo><mi>λ</mi><mo>)</mo></mrow>
        </mfrac>
      </mrow>
    </math>""",

    # Eq 7: Multi-state multinomial transition probability
    "multistate_prob": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msub><mi>p</mi><mrow><mi>i</mi><mi>m</mi></mrow></msub>
        <mo>=</mo>
        <mfrac>
          <mrow><mi>exp</mi><mo>(</mo><msub><mi>δ</mi><mi>m</mi></msub><mo>+</mo><msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><msub><mi>β</mi><mi>m</mi></msub><mo>+</mo><msub><mi>Z</mi><mi>t</mi></msub><msub><mi>γ</mi><mi>m</mi></msub><mo>+</mo><msub><mi>θ</mi><mi>m</mi></msub><mi>G</mi><mi>a</mi><msub><mi>p</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>)</mo></mrow>
          <mrow><munderover><mo>∑</mo><mrow><mi>j</mi><mo>=</mo><mn>0</mn></mrow><mn>4</mn></munderover><mi>exp</mi><mo>(</mo><msub><mi>δ</mi><mi>j</mi></msub><mo>+</mo><msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><msub><mi>β</mi><mi>j</mi></msub><mo>+</mo><msub><mi>Z</mi><mi>t</mi></msub><msub><mi>γ</mi><mi>j</mi></msub><mo>+</mo><msub><mi>θ</mi><mi>j</mi></msub><mi>G</mi><mi>a</mi><msub><mi>p</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>)</mo></mrow>
        </mfrac>
      </mrow>
    </math>""",

    # Eq 8: Fallen angel indicator
    "fallen_angel_def": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msubsup><mi>Y</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi><mo>+</mo><mn>4</mn></mrow><mi>FA</mi></msubsup>
        <mo>=</mo>
        <mrow>
          <mo>{</mo>
          <mtable columnalign="left">
            <mtr>
              <mtd><mn>1</mn></mtd>
              <mtd><mtext>if </mtext><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>≤</mo><mn>10</mn><mtext> and </mtext><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi><mo>+</mo><mn>4</mn></mrow></msub><mo>≥</mo><mn>11</mn><mspace width="0.5em"/><mtext>(BB+ or lower)</mtext></mtd>
            </mtr>
            <mtr>
              <mtd><mn>0</mn></mtd>
              <mtd><mtext>if </mtext><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub><mo>≤</mo><mn>10</mn><mtext> and </mtext><msub><mi>R</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi><mo>+</mo><mn>4</mn></mrow></msub><mo>≤</mo><mn>10</mn></mtd>
            </mtr>
          </mtable>
        </mrow>
      </mrow>
    </math>""",

    # Eq 9: Firth penalized likelihood
    "firth_loglik": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msup><mi>ℓ</mi><mo>*</mo></msup><mo>(</mo><mi>β</mi><mo>)</mo>
        <mo>=</mo>
        <mi>ℓ</mi><mo>(</mo><mi>β</mi><mo>)</mo>
        <mo>+</mo>
        <mfrac><mn>1</mn><mn>2</mn></mfrac><mi>ln</mi><mo>|</mo><mi mathvariant="script">I</mi><mo>(</mo><mi>β</mi><mo>)</mo><mo>|</mo>
      </mrow>
    </math>""",

    # Eq 10: VAR(2) system
    "var_system": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msub><mi>Z</mi><mi>t</mi></msub>
        <mo>=</mo>
        <mi>c</mi>
        <mo>+</mo>
        <munderover><mo>∑</mo><mrow><mi>l</mi><mo>=</mo><mn>1</mn></mrow><mn>2</mn></munderover>
        <msub><mi>A</mi><mi>l</mi></msub><msub><mi>Z</mi><mrow><mi>t</mi><mo>−</mo><mi>l</mi></mrow></msub>
        <mo>+</mo>
        <msub><mi>ϵ</mi><mi>t</mi></msub>
        <mo>,</mo><mspace width="1em"/>
        <msub><mi>ϵ</mi><mi>t</mi></msub>
        <mo>∼</mo>
        <mi mathvariant="script">N</mi><mo>(</mo><mn>0</mn><mo>,</mo><mi>Σ</mi><mo>)</mo>
      </mrow>
    </math>""",

    # Eq 11: Reverse stress test
    "reverse_stress": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <munder><mi>min</mi><msub><mi>ϵ</mi><mrow><mi>T</mi><mo>+</mo><mn>1</mn><mo>:</mo><mi>T</mi><mo>+</mo><mn>8</mn></mrow></msub></munder>
        <mspace width="0.5em"/>
        <munderover><mo>∑</mo><mrow><mi>h</mi><mo>=</mo><mn>1</mn></mrow><mn>8</mn></munderover>
        <msubsup><mi>ϵ</mi><mrow><mi>T</mi><mo>+</mo><mi>h</mi></mrow><mo>′</mo></msubsup>
        <msup><mi>Σ</mi><mrow><mo>−</mo><mn>1</mn></mrow></msup>
        <msub><mi>ϵ</mi><mrow><mi>T</mi><mo>+</mo><mi>h</mi></mrow></msub>
        <mspace width="1em"/><mtext>subject to</mtext><mspace width="1em"/>
        <mfrac><mn>1</mn><msub><mi>N</mi><mi>IG</mi></msub></mfrac>
        <munder><mo>∑</mo><mrow><mi>i</mi><mo>∈</mo><mi>IG</mi></mrow></munder>
        <mover><mi>P</mi><mo>^</mo></mover><mo>(</mo><msubsup><mi>Y</mi><mrow><mi>i</mi><mo>,</mo><mi>T</mi><mo>+</mo><mn>8</mn></mrow><mi>FA</mi></msubsup><mo>=</mo><mn>1</mn><mo>∣</mo><msub><mi>Z</mi><mrow><mi>T</mi><mo>+</mo><mn>8</mn></mrow></msub><mo>(</mo><msup><mi>ϵ</mi><mo>*</mo></msup><mo>)</mo><mo>)</mo>
        <mo>≥</mo>
        <mover><mi>π</mi><mo>¯</mo></mover>
      </mrow>
    </math>""",

    # Appendix A.1: Ordered Probit Sample Log-Likelihood
    "app_probit_loglik": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mi>ln</mi><mi mathvariant="script">L</mi><mo>(</mo><mi>β</mi><mo>,</mo><mi mathvariant="bold-italic">μ</mi><mo>)</mo>
        <mo>=</mo>
        <munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>N</mi></munderover>
        <munderover><mo>∑</mo><mrow><mi>k</mi><mo>=</mo><mn>1</mn></mrow><mi>K</mi></munderover>
        <msub><mi>d</mi><mrow><mi>i</mi><mi>k</mi></mrow></msub>
        <mi>ln</mi><mo>[</mo>
          <mi>Φ</mi><mo>(</mo><msub><mi>μ</mi><mi>k</mi></msub><mo>−</mo><msubsup><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>′</mo></msubsup><mi>β</mi><mo>)</mo>
          <mo>−</mo>
          <mi>Φ</mi><mo>(</mo><msub><mi>μ</mi><mrow><mi>k</mi><mo>−</mo><mn>1</mn></mrow></msub><mo>−</mo><msubsup><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>′</mo></msubsup><mi>β</mi><mo>)</mo>
        <mo>]</mo>
      </mrow>
    </math>""",

    # Appendix A.2: FOC wrt Beta
    "app_foc_beta": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mfrac><mrow><mo>∂</mo><mi>ln</mi><mi mathvariant="script">L</mi></mrow><mrow><mo>∂</mo><mi>β</mi></mrow></mfrac>
        <mo>=</mo>
        <munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>N</mi></munderover>
        <munderover><mo>∑</mo><mrow><mi>k</mi><mo>=</mo><mn>1</mn></mrow><mi>K</mi></munderover>
        <msub><mi>d</mi><mrow><mi>i</mi><mi>k</mi></mrow></msub>
        <mfrac>
          <mrow><mi>ϕ</mi><mo>(</mo><msub><mi>μ</mi><mrow><mi>k</mi><mo>−</mo><mn>1</mn></mrow></msub><mo>−</mo><msubsup><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>′</mo></msubsup><mi>β</mi><mo>)</mo><mo>−</mo><mi>ϕ</mi><mo>(</mo><msub><mi>μ</mi><mi>k</mi></msub><mo>−</mo><msubsup><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>′</mo></msubsup><mi>β</mi><mo>)</mo></mrow>
          <mrow><mi>Φ</mi><mo>(</mo><msub><mi>μ</mi><mi>k</mi></msub><mo>−</mo><msubsup><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>′</mo></msubsup><mi>β</mi><mo>)</mo><mo>−</mo><mi>Φ</mi><mo>(</mo><msub><mi>μ</mi><mrow><mi>k</mi><mo>−</mo><mn>1</mn></mrow></msub><mo>−</mo><msubsup><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>′</mo></msubsup><mi>β</mi><mo>)</mo></mrow>
        </mfrac>
        <msub><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow></msub>
        <mo>=</mo><mn>0</mn>
      </mrow>
    </math>""",

    # Appendix A.3: FOC wrt Cutpoint Mu
    "app_foc_mu": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mfrac><mrow><mo>∂</mo><mi>ln</mi><mi mathvariant="script">L</mi></mrow><mrow><mo>∂</mo><msub><mi>μ</mi><mi>k</mi></msub></mrow></mfrac>
        <mo>=</mo>
        <munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>N</mi></munderover>
        <mo>[</mo>
          <msub><mi>d</mi><mrow><mi>i</mi><mi>k</mi></mrow></msub>
          <mfrac><mrow><mi>ϕ</mi><mo>(</mo><msub><mi>μ</mi><mi>k</mi></msub><mo>−</mo><msubsup><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>′</mo></msubsup><mi>β</mi><mo>)</mo></mrow><msub><mi>P</mi><mrow><mi>i</mi><mi>k</mi></mrow></msub></mfrac>
          <mo>−</mo>
          <msub><mi>d</mi><mrow><mi>i</mi><mo>,</mo><mi>k</mi><mo>+</mo><mn>1</mn></mrow></msub>
          <mfrac><mrow><mi>ϕ</mi><mo>(</mo><msub><mi>μ</mi><mi>k</mi></msub><mo>−</mo><msubsup><mi>X</mi><mrow><mi>i</mi><mo>,</mo><mi>t</mi></mrow><mo>′</mo></msubsup><mi>β</mi><mo>)</mo></mrow><msub><mi>P</mi><mrow><mi>i</mi><mo>,</mo><mi>k</mi><mo>+</mo><mn>1</mn></mrow></msub></mfrac>
        <mo>]</mo>
        <mo>=</mo><mn>0</mn>
      </mrow>
    </math>""",

    # Appendix B.1: Firth modified score
    "app_firth_score": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msubsup><mi>U</mi><mi>j</mi><mo>*</mo></msubsup><mo>(</mo><mi>β</mi><mo>)</mo>
        <mo>=</mo>
        <mfrac><mrow><mo>∂</mo><msup><mi>ℓ</mi><mo>*</mo></msup></mrow><mrow><mo>∂</mo><msub><mi>β</mi><mi>j</mi></msub></mrow></mfrac>
        <mo>=</mo>
        <munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>N</mi></munderover>
        <mo>[</mo>
          <msub><mi>y</mi><mi>i</mi></msub><mo>−</mo><msub><mi>π</mi><mi>i</mi></msub>
          <mo>+</mo>
          <msub><mi>h</mi><mi>i</mi></msub><mo>(</mo><mfrac><mn>1</mn><mn>2</mn></mfrac><mo>−</mo><msub><mi>π</mi><mi>i</mi></msub><mo>)</mo>
        <mo>]</mo>
        <msub><mi>X</mi><mrow><mi>i</mi><mi>j</mi></mrow></msub>
        <mo>=</mo><mn>0</mn>
      </mrow>
    </math>""",

    # Appendix C.1: Continuous time ODE
    "app_partial_ode": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mfrac><mrow><mi>d</mi><mi>R</mi><mo>(</mo><mi>t</mi><mo>)</mo></mrow><mrow><mi>d</mi><mi>t</mi></mrow></mfrac>
        <mo>=</mo>
        <mi>κ</mi><mo>[</mo><mi>S</mi><mo>(</mo><mi>t</mi><mo>)</mo><mo>−</mo><mi>R</mi><mo>(</mo><mi>t</mi><mo>)</mo><mo>]</mo>
        <mo>,</mo><mspace width="1em"/>
        <mi>κ</mi><mo>&gt;</mo><mn>0</mn>
      </mrow>
    </math>""",

    # Appendix C.2: ODE solution
    "app_partial_sol": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mi>R</mi><mo>(</mo><mi>t</mi><mo>)</mo>
        <mo>=</mo>
        <mover><mi>S</mi><mo>¯</mo></mover>
        <mo>+</mo>
        <mo>(</mo><mi>R</mi><mo>(</mo><mn>0</mn><mo>)</mo><mo>−</mo><mover><mi>S</mi><mo>¯</mo></mover><mo>)</mo>
        <msup><mi>e</mi><mrow><mo>−</mo><mi>κ</mi><mi>t</mi></mrow></msup>
      </mrow>
    </math>""",

    # Appendix C.3: Half-life derivation
    "app_half_life_proof": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msup><mi>e</mi><mrow><mo>−</mo><mi>κ</mi><msub><mi>t</mi><mrow><mn>1</mn><mo>/</mo><mn>2</mn></mrow></msub></mrow></msup>
        <mo>=</mo>
        <mfrac><mn>1</mn><mn>2</mn></mfrac>
        <mspace width="1em"/><mo>⟹</mo><mspace width="1em"/>
        <msub><mi>t</mi><mrow><mn>1</mn><mo>/</mo><mn>2</mn></mrow></msub>
        <mo>=</mo>
        <mfrac><mrow><mi>ln</mi><mo>(</mo><mn>2</mn><mo>)</mo></mrow><mi>κ</mi></mfrac>
      </mrow>
    </math>""",

    # Appendix D.1: Structural VAR
    "app_var_structural": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msub><mi>A</mi><mn>0</mn></msub><msub><mi>Z</mi><mi>t</mi></msub>
        <mo>=</mo>
        <munderover><mo>∑</mo><mrow><mi>l</mi><mo>=</mo><mn>1</mn></mrow><mi>p</mi></munderover>
        <msub><mi>A</mi><mi>l</mi></msub><msub><mi>Z</mi><mrow><mi>t</mi><mo>−</mo><mi>l</mi></mrow></msub>
        <mo>+</mo>
        <msub><mi>ϵ</mi><mi>t</mi></msub>
        <mo>,</mo><mspace width="1em"/>
        <msub><mi>ϵ</mi><mi>t</mi></msub>
        <mo>∼</mo>
        <mi mathvariant="script">N</mi><mo>(</mo><mn>0</mn><mo>,</mo><msub><mi>I</mi><mi>k</mi></msub><mo>)</mo>
      </mrow>
    </math>""",

    # Appendix D.2: Moving Average representation
    "app_var_ma": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msub><mi>Z</mi><mrow><mi>T</mi><mo>+</mo><mi>h</mi></mrow></msub>
        <mo>=</mo>
        <munderover><mo>∑</mo><mrow><mi>j</mi><mo>=</mo><mn>0</mn></mrow><mrow><mi>h</mi><mo>−</mo><mn>1</mn></mrow></munderover>
        <msub><mi>C</mi><mi>j</mi></msub><msub><mi>ϵ</mi><mrow><mi>T</mi><mo>+</mo><mi>h</mi><mo>−</mo><mi>j</mi></mrow></msub>
        <mo>+</mo>
        <msub><mi mathvariant="double-struck">E</mi><mi>T</mi></msub><mo>[</mo><msub><mi>Z</mi><mrow><mi>T</mi><mo>+</mo><mi>h</mi></mrow></msub><mo>]</mo>
      </mrow>
    </math>""",

    # Appendix D.3: Stacked linear system
    "app_var_stacked": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mi mathvariant="bold">Z</mi>
        <mo>=</mo>
        <mi mathvariant="bold">C</mi><mi mathvariant="bold-italic">ϵ</mi>
        <mo>+</mo>
        <msub><mi mathvariant="bold">Z</mi><mn>0</mn></msub>
      </mrow>
    </math>""",

    # Appendix D.4: Linear constraints
    "app_var_constraints": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <mi>R</mi><mi mathvariant="bold">C</mi><mi mathvariant="bold-italic">ϵ</mi>
        <mo>=</mo>
        <mi>r</mi><mo>−</mo><mi>R</mi><msub><mi mathvariant="bold">Z</mi><mn>0</mn></msub>
        <mo>≡</mo>
        <mi mathvariant="bold">q</mi>
      </mrow>
    </math>""",

    # Appendix D.5: Minimum energy shock solution
    "app_var_energy": """<math xmlns="http://www.w3.org/1998/Math/MathML">
      <mrow>
        <msup><mi mathvariant="bold-italic">ϵ</mi><mo>*</mo></msup>
        <mo>=</mo>
        <mo>(</mo><mi>R</mi><mi mathvariant="bold">C</mi><msup><mo>)</mo><mo>′</mo></msup>
        <mo>[</mo>
          <mo>(</mo><mi>R</mi><mi mathvariant="bold">C</mi><mo>)</mo>
          <mo>(</mo><mi>R</mi><mi mathvariant="bold">C</mi><msup><mo>)</mo><mo>′</mo></msup>
        <msup><mo>]</mo><mrow><mo>−</mo><mn>1</mn></mrow></msup>
        <mi mathvariant="bold">q</mi>
      </mrow>
    </math>""",
}


def match_equation_key(eq_str: str) -> tuple[str, str]:
    """Identify the exact MathML template and equation tag for a markdown equation block."""
    clean = eq_str.replace("$$", "").strip()

    # Match equation tag if present
    tag = ""
    tag_m = re.search(r"\\tag\{([^}]+)\}", clean)
    if tag_m:
        tag = f"({tag_m.group(1)})"

    if "y_{i,t}^*" in clean and "\\beta" in clean and "\\alpha_s" in clean:
        return "latent_credit", tag or "(1)"
    elif "R_{i,t} = k" in clean and "\\mu_{k-1}" in clean:
        return "cutpoint_mapping", tag or "(2)"
    elif "P(R_{i,t} = k" in clean and "\\Phi" in clean:
        return "probit_prob", tag or "(3)"
    elif "S_{i,t} \\equiv" in clean or "S_{i,t} =" in clean:
        return "shadow_rating", tag or "(4)"
    elif "\\Delta R_{i,t}" in clean and "\\lambda" in clean:
        return "partial_adjustment", tag or "(5)"
    elif "t_{1/2} =" in clean and "\\ln(0.5)" in clean:
        return "rating_half_life", tag or "(6)"
    elif "p_{im} =" in clean and "\\exp" in clean:
        return "multistate_prob", tag or "(7)"
    elif "Y_{i,t+4}^{FA}" in clean:
        return "fallen_angel_def", tag or "(8)"
    elif "\\ell^*(\\beta)" in clean and "\\mathcal{I}" in clean:
        return "firth_loglik", tag or "(9)"
    elif "Z_t = c +" in clean and "\\sum" in clean:
        return "var_system", tag or "(10)"
    elif "\\min_{\\epsilon" in clean and "\\Sigma^{-1}" in clean:
        return "reverse_stress", tag or "(11)"
    elif "\\ln \\mathcal{L}(\\beta" in clean and "\\Phi" in clean:
        return "app_probit_loglik", tag or "(A.1)"
    elif "\\frac{\\partial \\ln \\mathcal{L}}{\\partial \\beta}" in clean:
        return "app_foc_beta", tag or "(A.2)"
    elif "\\frac{\\partial \\ln \\mathcal{L}}{\\partial \\mu_k}" in clean:
        return "app_foc_mu", tag or "(A.3)"
    elif "U_j^*(\\beta)" in clean:
        return "app_firth_score", tag or "(B.2)"
    elif "\\frac{d R(t)}{dt}" in clean:
        return "app_partial_ode", tag or "(C.1)"
    elif "R(t) = \\bar{S}" in clean:
        return "app_partial_sol", tag or "(C.2)"
    elif "e^{-\\kappa t_{1/2}}" in clean:
        return "app_half_life_proof", tag or "(C.3)"
    elif "A_0 Z_t =" in clean:
        return "app_var_structural", tag or "(D.1)"
    elif "Z_{T+h} =" in clean and "\\mathbb{E}_T" in clean:
        return "app_var_ma", tag or "(D.2)"
    elif "\\mathbf{Z} = \\mathbf{C}" in clean:
        return "app_var_stacked", tag or "(D.3)"
    elif "R \\mathbf{C} \\boldsymbol{\\epsilon}" in clean:
        return "app_var_constraints", tag or "(D.4)"
    elif "\\boldsymbol{\\epsilon}^* =" in clean:
        return "app_var_energy", tag or "(D.5)"

    return "", tag


# Greek and mathematical symbols mapping for inline math rendering
GREEK_MAP = {
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\psi": "ψ",
    r"\lambda": "λ",
    r"\sigma": "σ",
    r"\Sigma": "Σ",
    r"\rho": "ρ",
    r"\epsilon": "ε",
    r"\eta": "η",
    r"\Delta": "Δ",
    r"\chi": "χ",
    r"\mu": "μ",
    r"\theta": "θ",
    r"\kappa": "κ",
    r"\pi": "π",
    r"\Phi": "Φ",
    r"\phi": "ϕ",
}

SYMBOL_MAP = {
    r"\ge": "≥",
    r"\le": "≤",
    r"\sim": "∼",
    r"\equiv": "≡",
    r"\implies": "⟹",
    r"\iff": "⟺",
    r"\times": "×",
    r"\pm": "±",
    r"\cdot": "·",
    r"\partial": "∂",
    r"\quad": " ",
    r"\mathbf{1}": "1",
    r"\sum": "∑",
    r"\dots": "…",
    r"\cdots": "…",
    r"\approx": "≈",
    r"\ne": "≠",
    r"\neq": "≠",
    r"\in": "∈",
    r"\infty": "∞",
}


def clean_inline_latex(s: str) -> str:
    """Normalize LaTeX commands to clean unicode string before subscript/superscript parsing."""
    s = s.strip()
    s = re.sub(r"\\left|\\right", "", s)
    s = re.sub(r"\\Big\||\\Bigg/|\\Big", "", s)
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\mathbf\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\mathcal\{([A-Za-z])\}", r"\1", s)
    s = re.sub(r"\\mathbb\{([A-Za-z])\}", r"\1", s)
    s = re.sub(r"\\frac\{1\}\{([^}]+)\}", r"1/\1", s)
    s = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"\1/\2", s)
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"√(\1)", s)
    s = s.replace(r"\hat{P}", "P̂").replace(r"\bar{\pi}", "π̄")
    s = s.replace(r"\hat{\beta}", "β̂").replace(r"\bar{\beta}", "β̄")
    s = s.replace(r"\bar{S}", "S̄")

    for k, v in GREEK_MAP.items():
        s = re.sub(re.escape(k) + r"(?![A-Za-z])", v, s)

    for k, v in SYMBOL_MAP.items():
        s = re.sub(re.escape(k) + r"(?![A-Za-z])", v, s)

    s = re.sub(r"\\tag\{[^}]*\}", "", s)
    s = re.sub(r"\\([A-Za-z]+)", r"\1", s)
    return s.strip()


# Table schemas: column widths and summary row prefixes (pure black IEEE booktabs)
TABLE_SCHEMAS = {
    "EXECUTIVE SCORECARD": {
        "widths": [Inches(1.6), Inches(1.8), Inches(1.5), Inches(1.8)],
        "align_right": [1, 2],
        "font_size": Pt(8.0),
        "padding_lr": 40,
    },
    "STRUCTURE OF THE RESEARCH INVESTIGATION": {
        "widths": [Inches(1.2), Inches(4.5), Inches(1.0)],
        "align_right": [2],
        "font_size": Pt(8.0),
        "padding_lr": 40,
    },
    "TABLE I": {
        "widths": [Inches(3.20), Inches(1.10), Inches(1.20), Inches(1.20)],
        "align_right": [1, 2, 3],
        "font_size": Pt(8.0),
        "padding_lr": 45,
    },
    "TABLE II": {
        "widths": [Inches(1.66), Inches(0.72), Inches(0.72), Inches(0.72), Inches(0.72), Inches(0.72), Inches(0.72), Inches(0.72)],
        "align_right": [1, 2, 3, 4, 5, 6, 7],
        "font_size": Pt(7.0),
        "padding_lr": 25,
    },
    "TABLE III": {
        "widths": [Inches(2.50), Inches(1.40), Inches(1.40), Inches(1.40)],
        "align_right": [1, 2, 3],
        "font_size": Pt(8.0),
        "padding_lr": 45,
    },
    "TABLE IV": {
        "widths": [Inches(2.50), Inches(1.40), Inches(1.40), Inches(1.40)],
        "align_right": [1, 2, 3],
        "font_size": Pt(8.0),
        "padding_lr": 45,
    },
    "TABLE V": {
        "widths": [Inches(2.20), Inches(1.10), Inches(1.60), Inches(1.80)],
        "align_right": [1, 2, 3],
        "font_size": Pt(8.0),
        "padding_lr": 45,
    },
    "TABLE VI": {
        "widths": [Inches(2.70), Inches(1.00), Inches(1.00), Inches(1.00), Inches(1.00)],
        "align_right": [1, 2, 3, 4],
        "font_size": Pt(7.5),
        "padding_lr": 35,
    },
    "TABLE VII": {
        "widths": [Inches(2.50), Inches(0.84), Inches(0.84), Inches(0.84), Inches(0.84), Inches(0.84)],
        "align_right": [1, 2, 3, 4, 5],
        "font_size": Pt(7.0),
        "padding_lr": 25,
    },
    "TABLE VIII": {
        "widths": [Inches(0.80), Inches(0.70), Inches(0.80), Inches(0.90), Inches(0.90), Inches(0.90), Inches(0.80), Inches(0.90)],
        "align_right": [1, 2, 3, 4, 5, 6, 7],
        "font_size": Pt(7.0),
        "padding_lr": 25,
    },
    "TABLE IX": {
        "widths": [Inches(1.90), Inches(0.60), Inches(0.60), Inches(0.60), Inches(0.60), Inches(0.60), Inches(0.60), Inches(0.60), Inches(0.60)],
        "align_right": [1, 2, 3, 4, 5, 6, 7, 8],
        "font_size": Pt(6.5),
        "padding_lr": 20,
    },
    "TABLE X": {
        "widths": [Inches(4.00), Inches(1.10), Inches(1.60)],
        "align_right": [1, 2],
        "font_size": Pt(8.0),
        "padding_lr": 45,
    },
}


def set_cell_margins(cell, top=50, bottom=50, left=80, right=80):
    """Set inner cell padding in twips (20 twips = 1 pt)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'''<w:tcMar xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:top w:w="{top}" w:type="dxa"/>
        <w:bottom w:w="{bottom}" w:type="dxa"/>
        <w:left w:w="{left}" w:type="dxa"/>
        <w:right w:w="{right}" w:type="dxa"/>
    </w:tcMar>''')
    tcPr.append(tcMar)


class WordReportBuilder:
    def __init__(self):
        self.doc = docx.Document()
        self.xsl_path = find_mml2omml_xsl()
        self.xslt = ET.parse(str(self.xsl_path))
        self.transform = ET.XSLT(self.xslt)

        self._configure_page_setup()
        self._configure_styles()
        self._configure_header_footer()

    def _configure_page_setup(self):
        section = self.doc.sections[0]
        # Standard A4
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        # 0.75-inch margins (pure IEEE)
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
        section.different_first_page_header_footer = True

    def _configure_styles(self):
        # Configure Normal Style: Times New Roman, 10 pt, Pure Black (NO COLORS)
        normal_style = self.doc.styles["Normal"]
        normal_style.font.name = "Times New Roman"
        normal_style.font.size = Pt(10)
        normal_style.font.color.rgb = RGBColor(0, 0, 0)
        normal_style.paragraph_format.line_spacing = 1.15
        normal_style.paragraph_format.space_after = Pt(4)
        normal_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def _configure_header_footer(self):
        section = self.doc.sections[0]

        # Running Header: Cleared (clean title page)
        header = section.header
        p_head = header.paragraphs[0]
        p_head.text = ""

        # Running Footer (Pages 2+): Pure black typography & rule
        footer = section.footer
        p_foot = footer.paragraphs[0]
        p_foot.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_foot.paragraph_format.space_before = Pt(4)

        r_f1 = p_foot.add_run("QUANTITATIVE ANALYSIS OF FINANCIAL MARKETS | SMU MSc Quantitative Finance")
        r_f1.font.name = "Times New Roman"
        r_f1.font.size = Pt(8.5)
        r_f1.font.color.rgb = RGBColor(0, 0, 0)

        r_ftab = p_foot.add_run("\t\tPage ")
        r_ftab.font.name = "Times New Roman"
        r_ftab.font.size = Pt(8.5)
        r_ftab.font.color.rgb = RGBColor(0, 0, 0)

        # Page Number Field
        fldSimple = parse_xml(r'<w:fldSimple xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:instr="PAGE"/>')
        p_foot._p.append(fldSimple)

        # Top border on footer (pure black rule)
        fPr = p_foot._p.get_or_add_pPr()
        fBdr = parse_xml(r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:top w:val="single" w:sz="4" w:space="1" w:color="000000"/></w:pBdr>')
        fPr.append(fBdr)

    def add_title_block(self, page_map: dict = None):
        """Build front matter: Title, Authors, Abstract, Index Terms, and TOC on Page 1."""
        # Title (Pure Black, 15 pt Bold)
        p_title = self.doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_title.paragraph_format.space_before = Pt(10)
        p_title.paragraph_format.space_after = Pt(5)
        r_title = p_title.add_run("MACRO-SENSITIVITY OF CORPORATE CREDIT RATINGS & FALLEN-ANGEL EARLY WARNING")
        r_title.font.name = "Times New Roman"
        r_title.font.size = Pt(15)
        r_title.font.bold = True
        r_title.font.color.rgb = RGBColor(0, 0, 0)

        # Subtitle (Pure Black, 10 pt Italic)
        p_sub = self.doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_sub.paragraph_format.space_after = Pt(6)
        r_sub = p_sub.add_run("A Point-in-Time Econometric Framework with CreditWatch Transitions and Coherent Macro Stress Testing")
        r_sub.font.name = "Times New Roman"
        r_sub.font.size = Pt(10)
        r_sub.font.italic = True
        r_sub.font.color.rgb = RGBColor(0, 0, 0)

        # Author Team Block (Pure Black)
        p_auth = self.doc.add_paragraph()
        p_auth.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_auth.paragraph_format.space_after = Pt(6)
        r_a1 = p_auth.add_run("Mahir Mehta, Kunj Maheshwari, Manan Chandarana, Bhumika Agrawal, Kashish Seth\n")
        r_a1.font.name = "Times New Roman"
        r_a1.font.size = Pt(10.5)
        r_a1.font.bold = True
        r_a1.font.color.rgb = RGBColor(0, 0, 0)
        r_a2 = p_auth.add_run("MASTER OF SCIENCE IN QUANTITATIVE FINANCE | QUANTITATIVE ANALYSIS OF FINANCIAL MARKETS\nSINGAPORE MANAGEMENT UNIVERSITY")
        r_a2.font.name = "Times New Roman"
        r_a2.font.size = Pt(9.5)
        r_a2.font.italic = True
        r_a2.font.color.rgb = RGBColor(0, 0, 0)

        # Thin black rule
        p_rule2 = self.doc.add_paragraph()
        p_rule2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_rule2.paragraph_format.space_after = Pt(5)
        pPr2 = p_rule2._p.get_or_add_pPr()
        pBdr2 = parse_xml(r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/></w:pBdr>')
        pPr2.append(pBdr2)

        # Abstract
        p_abs = self.doc.add_paragraph()
        p_abs.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_abs.paragraph_format.space_after = Pt(4)
        r_abs_h = p_abs.add_run("Abstract—")
        r_abs_h.font.name = "Times New Roman"
        r_abs_h.font.size = Pt(9)
        r_abs_h.font.bold = True
        r_abs_h.font.italic = True
        r_abs_h.font.color.rgb = RGBColor(0, 0, 0)

        r_abs_txt = p_abs.add_run(
            "Credit rating agencies officially adhere to a Through-The-Cycle (TTC) philosophy designed to insulate corporate "
            "debt issuers and credit markets from transient cyclical volatility. However, this intentional smoothing induces substantial rating stickiness, "
            "causing published agency grades to lag macroeconomic fundamentals by several quarters. This delay is particularly hazardous at the "
            "investment-grade boundary (BBB− to BB+), where fallen-angel downgrades trigger mandatory institutional divestment, secondary market liquidity "
            "evaporation, and discrete spikes in credit spreads. This study develops an end-to-end, point-in-time (PIT) econometric framework across an "
            "assembled longitudinal panel of 66,706 firm-quarters (698 non-financial, non-utility US corporate issuers; 103 calendar quarters spanning "
            "2000Q1–2025Q4) to quantify agency adjustment lags, evaluate the incremental explanatory power of macroeconomic and monetary policy conditioning "
            "variables, and construct an out-of-sample early-warning forecasting model for fallen-angel transitions.\n\n"
            "Our empirical discoveries establish five primary contributions: (i) In an Ordered Probit rating determinants architecture, a block Likelihood "
            "Ratio test on macroeconomic regressors yields χ² = 284.6 (p < 0.0001), decisively rejecting the hypothesis that agency ratings are macro-orthogonal; "
            "(ii) Modeling a point-in-time latent shadow rating reveals an agency partial adjustment speed of λ = 0.0100 per quarter, implying an aggregate "
            "rating adjustment half-life of 68.97 quarters (~17.2 years) that accelerates significantly to 3.92 quarters during tightening recessions; "
            "(iii) CreditWatch and Outlook placements represent highly informative intermediate migration states rather than ancillary footnotes, capturing "
            "18.8% of the panel and exhibiting severe asymmetry in downgrade hazard; (iv) On an embargoed out-of-sample test window (2020Q1–2025Q4; 14,403 "
            "firm-quarters; 204 realized fallen-angel events), a macro-augmented Firth penalized rare-event logistic model achieves an out-of-sample ROC-AUC "
            "of 0.8019, a Precision-Recall AUC of 0.0939 (under a 4.8% baseline event rate), a Brier calibration score of 0.0289, and a top-decile lift factor "
            "of 2.80×, while issuing advance warning alerts an average of 3.12 quarters prior to downgrade—delivering a net early-warning lead-time advantage of "
            "+1.88 quarters (~5.6 months) over published agency CreditWatch placements; and (v) Conditional VAR scenario projections (Waggoner & Zha, 1999) "
            "demonstrate that an 8-quarter +300 bp monetary tightening shock (S1) elevates the projected fallen-angel rate from 2.41% to 6.85% ($96.8 Billion debt-at-risk), "
            "while an analytical reverse stress test (N5) determines the joint macro shock path required to generate a crisis-level 12.00% fallen-angel rate "
            "($170.0 Billion debt-at-risk). Robustness checks, time-permuted placebo tests (AUC = 0.8043), and shuffled-label negative controls (AUC = 0.5036) "
            "verify that empirical gains are free from look-ahead leakage or spurious correlation."
        )
        r_abs_txt.font.name = "Times New Roman"
        r_abs_txt.font.size = Pt(8.5)
        r_abs_txt.font.color.rgb = RGBColor(0, 0, 0)

        # Index Terms
        p_idx = self.doc.add_paragraph()
        p_idx.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_idx.paragraph_format.space_after = Pt(6)
        r_idx_h = p_idx.add_run("Index Terms—")
        r_idx_h.font.name = "Times New Roman"
        r_idx_h.font.size = Pt(9)
        r_idx_h.font.bold = True
        r_idx_h.font.italic = True
        r_idx_h.font.color.rgb = RGBColor(0, 0, 0)

        r_idx_txt = p_idx.add_run(
            "Credit risk, through-the-cycle ratings, point-in-time shadow ratings, agency adjustment lag, fallen angels, investment-grade boundary, "
            "CreditWatch migrations, ordered probit, Firth penalized logistic regression, vector autoregression (VAR), reverse stress testing, financial stability."
        )
        r_idx_txt.font.name = "Times New Roman"
        r_idx_txt.font.size = Pt(8.5)
        r_idx_txt.font.italic = True
        r_idx_txt.font.color.rgb = RGBColor(0, 0, 0)

        # Thin black rule
        p_rule3 = self.doc.add_paragraph()
        p_rule3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_rule3.paragraph_format.space_after = Pt(5)
        pPr3 = p_rule3._p.get_or_add_pPr()
        pBdr3 = parse_xml(r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/></w:pBdr>')
        pPr3.append(pBdr3)

        # Table of Contents / Structure of Investigation
        p_toc_h = self.doc.add_paragraph()
        p_toc_h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_toc_h.paragraph_format.space_before = Pt(3)
        p_toc_h.paragraph_format.space_after = Pt(3)
        r_th = p_toc_h.add_run("STRUCTURE OF THE RESEARCH INVESTIGATION & ACADEMIC RUBRIC COMPLIANCE")
        r_th.font.name = "Times New Roman"
        r_th.font.size = Pt(8.5)
        r_th.font.bold = True
        r_th.font.color.rgb = RGBColor(0, 0, 0)

        if page_map is None:
            page_map = {
                "Section I": 2,
                "Section II": 3,
                "Section III": 5,
                "Section IV": 7,
                "Section V": 9,
                "Section VI": 11,
                "Section VII": 13,
                "Section VIII": 14,
                "Section IX": 15,
                "Appendix": 16,
                "References": 17,
            }

        toc_items = [
            ("Section I", "Introduction, Problem Formulation & Economic Significance", f"Page {page_map.get('Section I', 2)}"),
            ("Section II", "Theoretical Foundation, Latent Index & Econometric Formulation", f"Page {page_map.get('Section II', 3)}"),
            ("Section III", "Data Architecture, Longitudinal Panel Construction & Leakage Safeguards", f"Page {page_map.get('Section III', 5)}"),
            ("Section IV", "Empirical Results: Rating Determinants & Agency Adjustment Lag", f"Page {page_map.get('Section IV', 7)}"),
            ("Section V", "Out-of-Sample Fallen-Angel Early Warning & Advance Notice", f"Page {page_map.get('Section V', 9)}"),
            ("Section VI", "Coherent Macro Stress Testing & Systemic Financial Stability", f"Page {page_map.get('Section VI', 11)}"),
            ("Section VII", "Verification Rigor, Robustness Checks & Negative Controls", f"Page {page_map.get('Section VII', 13)}"),
            ("Section VIII", "Institutional Implementation, Fixed-Income Mandates & Policy Implications", f"Page {page_map.get('Section VIII', 14)}"),
            ("Section IX", "Conclusion & Concluding Remarks", f"Page {page_map.get('Section IX', 15)}"),
            ("Appendix", "Mathematical Derivations & Extended Econometric Proofs", f"Page {page_map.get('Appendix', 16)}"),
            ("References", "Complete Academic References & Bibliography", f"Page {page_map.get('References', 17)}"),
        ]

        tbl = self.doc.add_table(rows=len(toc_items), cols=3)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tblPr = tbl._tbl.tblPr
        bdr_xml = parse_xml(r'''<w:tblBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:top w:val="single" w:sz="6" w:space="0" w:color="000000"/>
            <w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>
            <w:left w:val="none"/><w:right w:val="none"/>
            <w:insideH w:val="none"/><w:insideV w:val="none"/>
        </w:tblBorders>''')
        tblPr.append(bdr_xml)

        col_w = [Inches(1.2), Inches(4.5), Inches(1.0)]
        for r_idx, (col1, col2, col3) in enumerate(toc_items):
            row = tbl.rows[r_idx]
            for c_idx, text in enumerate([col1, col2, col3]):
                cell = row.cells[c_idx]
                cell.width = col_w[c_idx]
                set_cell_margins(cell, top=25, bottom=25, left=40, right=40)
                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.05
                if c_idx == 0:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    r = p.add_run(text)
                    r.font.bold = True
                elif c_idx == 1:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    r = p.add_run(text)
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    r = p.add_run(text)
                r.font.name = "Times New Roman"
                r.font.size = Pt(8.0)
                r.font.color.rgb = RGBColor(0, 0, 0)

        self.doc.add_page_break()

    def add_heading_1(self, text: str, is_first: bool = False):
        if not is_first:
            self.doc.add_page_break()

        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True

        r = p.add_run(text.upper())
        r.font.name = "Times New Roman"
        r.font.size = Pt(11)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0, 0, 0)

    def add_heading_2(self, text: str):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(9)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.keep_with_next = True

        r = p.add_run(text)
        r.font.name = "Times New Roman"
        r.font.size = Pt(10.5)
        r.font.bold = True
        r.font.italic = True
        r.font.color.rgb = RGBColor(0, 0, 0)

    def add_heading_3(self, text: str):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.keep_with_next = True

        r = p.add_run(text)
        r.font.name = "Times New Roman"
        r.font.size = Pt(10)
        r.font.italic = True
        r.font.color.rgb = RGBColor(0, 0, 0)

    def add_inline_math_runs(self, p, math_content: str, font_size: Pt = Pt(10), bold: bool = False):
        """Renders an inline math expression into a docx Paragraph using pure black Times New Roman."""
        cleaned = clean_inline_latex(math_content)

        pattern = re.compile(r"(_\{[^}]+\}|_[A-Za-z0-9α-ωΑ-Ωβ̂β̄σ̂ρ̂z̄r̄ỹμλθκπε]|_M|_L|_H|\^\{[^}]+\}|\^[A-Za-z0-9\+\-α-ωΑ-Ω\*])")
        parts = pattern.split(cleaned)

        sub_size = Pt(font_size.pt * 0.82)

        for part in parts:
            if not part:
                continue
            if part.startswith("_"):
                sub_text = part[2:-1] if part.startswith("_{") and part.endswith("}") else part[1:]
                r = p.add_run(sub_text)
                r.font.name = "Times New Roman"
                r.font.size = sub_size
                r.font.subscript = True
                r.font.bold = bold
                r.font.color.rgb = RGBColor(0, 0, 0)
                if sub_text.isalpha() or re.match(r"^[α-ωΑ-Ωβ̂β̄σ̂ρ̂z̄r̄ỹμλθκπε]$", sub_text):
                    r.font.italic = True
            elif part.startswith("^"):
                sup_text = part[2:-1] if part.startswith("^{") and part.endswith("}") else part[1:]
                r = p.add_run(sup_text)
                r.font.name = "Times New Roman"
                r.font.size = sub_size
                r.font.superscript = True
                r.font.bold = bold
                r.font.color.rgb = RGBColor(0, 0, 0)
                if sup_text.isalpha() or re.match(r"^[α-ωΑ-Ωβ̂β̄σ̂ρ̂z̄r̄ỹμλθκπε]$", sup_text):
                    r.font.italic = True
            else:
                sub_tokens = re.findall(r"([A-Za-zα-ωΑ-Ωβ̂β̄σ̂ρ̂z̄r̄ỹμλθκπε]+|[^A-Za-zα-ωΑ-Ωβ̂β̄σ̂ρ̂z̄r̄ỹμλθκπε]+)", part)
                for st in sub_tokens:
                    r = p.add_run(st)
                    r.font.name = "Times New Roman"
                    r.font.size = font_size
                    r.font.bold = bold
                    r.font.color.rgb = RGBColor(0, 0, 0)
                    if re.match(r"^[A-Za-zα-ωΑ-Ωβ̂β̄σ̂ρ̂z̄r̄ỹμλθκπε]+$", st):
                        if st in ["Cov", "Var", "Corr", "rank", "ln", "exp", "max", "min", "High", "Low", "TED", "VIX", "bps", "P1", "P10", "df"]:
                            r.font.italic = False
                        else:
                            r.font.italic = True
                    else:
                        r.font.italic = False

    def add_paragraph_formatted(self, text: str):
        """Parse markdown bold/italic runs, lists, and math into justified IEEE paragraph."""
        if not text.strip():
            return

        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15

        # Check for list items
        if text.startswith("- ") or text.startswith("* "):
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.15)
            text = "• " + text[2:]
        elif re.match(r"^\d+\.\s+", text):
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.first_line_indent = Inches(-0.15)

        pattern = re.compile(r"(\*\*.*?\*\*|\*.*?\*|\$.*?\$|`.*?`)")
        tokens = pattern.split(text)

        for tok in tokens:
            if not tok:
                continue
            if tok.startswith("**") and tok.endswith("**"):
                inner = tok[2:-2]
                if "$" in inner:
                    inner_tokens = re.split(r"(\$.*?\$)", inner)
                    for itok in inner_tokens:
                        if not itok:
                            continue
                        if itok.startswith("$") and itok.endswith("$"):
                            self.add_inline_math_runs(p, itok[1:-1], font_size=Pt(10), bold=True)
                        else:
                            r = p.add_run(itok)
                            r.font.name = "Times New Roman"
                            r.font.size = Pt(10)
                            r.font.bold = True
                            r.font.color.rgb = RGBColor(0, 0, 0)
                else:
                    r = p.add_run(inner)
                    r.font.name = "Times New Roman"
                    r.font.size = Pt(10)
                    r.font.bold = True
                    r.font.color.rgb = RGBColor(0, 0, 0)
            elif tok.startswith("*") and tok.endswith("*") and not tok.startswith("**"):
                inner = tok[1:-1]
                if "$" in inner:
                    inner_tokens = re.split(r"(\$.*?\$)", inner)
                    for itok in inner_tokens:
                        if not itok:
                            continue
                        if itok.startswith("$") and itok.endswith("$"):
                            self.add_inline_math_runs(p, itok[1:-1], font_size=Pt(10))
                        else:
                            r = p.add_run(itok)
                            r.font.name = "Times New Roman"
                            r.font.size = Pt(10)
                            r.font.italic = True
                            r.font.color.rgb = RGBColor(0, 0, 0)
                else:
                    r = p.add_run(inner)
                    r.font.name = "Times New Roman"
                    r.font.size = Pt(10)
                    r.font.italic = True
                    r.font.color.rgb = RGBColor(0, 0, 0)
            elif tok.startswith("$") and tok.endswith("$"):
                self.add_inline_math_runs(p, tok[1:-1], font_size=Pt(10))
            elif tok.startswith("`") and tok.endswith("`"):
                r = p.add_run(tok[1:-1])
                r.font.name = "Consolas"
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(0, 0, 0)
            else:
                r = p.add_run(tok)
                r.font.name = "Times New Roman"
                r.font.size = Pt(10)
                r.font.color.rgb = RGBColor(0, 0, 0)

    def add_equation_omml(self, eq_text: str):
        """Convert LaTeX equation block into native Word OMML and embed with right-aligned tag."""
        key, tag = match_equation_key(eq_text)
        if not key or key not in MATHML_MAP:
            # Fallback to centered italic text
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            r = p.add_run(eq_text.replace("$$", "").strip())
            r.font.name = "Times New Roman"
            r.font.italic = True
            r.font.size = Pt(10)
            r.font.color.rgb = RGBColor(0, 0, 0)
            return

        mml_str = MATHML_MAP[key]
        mml_root = ET.fromstring(mml_str)
        omml_tree = self.transform(mml_root)
        omml_xml = ET.tostring(omml_tree, encoding="utf-8").decode("utf-8")

        if tag:
            tbl = self.doc.add_table(rows=1, cols=2)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            tbl.autofit = False

            tblPr = tbl._tbl.tblPr
            bdr_xml = parse_xml(r'''<w:tblBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:top w:val="none"/><w:left w:val="none"/><w:bottom w:val="none"/>
                <w:right w:val="none"/><w:insideH w:val="none"/><w:insideV w:val="none"/>
            </w:tblBorders>''')
            tblPr.append(bdr_xml)

            c_eq, c_tag = tbl.rows[0].cells
            c_eq.width = Inches(5.9)
            c_tag.width = Inches(0.8)

            p_eq = c_eq.paragraphs[0]
            p_eq.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_eq.paragraph_format.space_before = Pt(4)
            p_eq.paragraph_format.space_after = Pt(4)
            p_eq._p.append(parse_xml(omml_xml))

            p_tag = c_tag.paragraphs[0]
            p_tag.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p_tag.paragraph_format.space_before = Pt(4)
            p_tag.paragraph_format.space_after = Pt(4)
            r_t = p_tag.add_run(tag)
            r_t.font.name = "Times New Roman"
            r_t.font.size = Pt(10)
            r_t.font.color.rgb = RGBColor(0, 0, 0)
        else:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            p._p.append(parse_xml(omml_xml))

    def add_table_block(self, text: str):
        """Convert Markdown/ASCII table block into formal IEEE Booktabs Word table (pure black, no colors)."""
        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        if not lines:
            return

        caption = ""
        footnotes = []
        raw_rows = []

        for line in lines:
            if line.upper().startswith("TABLE") or line.upper().startswith("EXECUTIVE SCORECARD") or line.upper().startswith("STRUCTURE OF"):
                caption = line
            elif line.startswith("*Note:*") or line.startswith("Note:") or line.startswith("* p <") or line.startswith("Breakeven") or line.startswith("Sample Period"):
                fn_clean = line.replace("*Note:*", "Note:").replace("*", "")
                footnotes.append(fn_clean)
            elif line.startswith("|:---") or line.startswith("---") or line.startswith("==="):
                continue
            elif "|" in line:
                cells = [c.strip() for c in line.split("|")]
                if cells and cells[0] == "":
                    cells = cells[1:]
                if cells and cells[-1] == "":
                    cells = cells[:-1]
                if cells and not cells[0].startswith("---") and not cells[0].startswith(":---"):
                    raw_rows.append(cells)
            else:
                cells = re.split(r"\s{2,}", line)
                if cells:
                    raw_rows.append(cells)

        if not raw_rows:
            return

        # Identify table key with robust matching
        matched_key = ""
        m_roman = re.match(r"^(TABLE\s+[IVXLCDM]+)\b", caption.strip(), re.IGNORECASE)
        if m_roman:
            cand = m_roman.group(1).upper()
            if cand in TABLE_SCHEMAS:
                matched_key = cand
        if not matched_key:
            for k in sorted(TABLE_SCHEMAS.keys(), key=lambda x: -len(x)):
                if re.search(r"\b" + re.escape(k) + r"\b", caption.upper()):
                    matched_key = k
                    break

        schema = TABLE_SCHEMAS.get(matched_key, {})
        col_widths = schema.get("widths", [])
        align_right_cols = schema.get("align_right", [])
        font_size = schema.get("font_size", Pt(8.0))
        cell_pad_lr = schema.get("padding_lr", 40)

        # Caption (Centered IEEE style, pure black)
        if caption:
            parts = caption.split(":", 1)
            p_c1 = self.doc.add_paragraph()
            p_c1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_c1.paragraph_format.space_before = Pt(11)
            p_c1.paragraph_format.space_after = Pt(1.5)
            p_c1.paragraph_format.keep_with_next = True
            r1 = p_c1.add_run(parts[0].strip().upper())
            r1.font.name = "Times New Roman"
            r1.font.size = Pt(9)
            r1.font.bold = True
            r1.font.color.rgb = RGBColor(0, 0, 0)

            if len(parts) > 1:
                p_c2 = self.doc.add_paragraph()
                p_c2.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_c2.paragraph_format.space_after = Pt(4)
                p_c2.paragraph_format.keep_with_next = True
                r2 = p_c2.add_run(parts[1].strip().upper())
                r2.font.name = "Times New Roman"
                r2.font.size = Pt(8.5)
                r2.font.color.rgb = RGBColor(0, 0, 0)

        num_cols = max(len(r) for r in raw_rows)
        for r in raw_rows:
            while len(r) < num_cols:
                r.append("")

        # Fallback to evenly distributing 6.70 inches if widths count mismatch
        if not col_widths or len(col_widths) != num_cols:
            if num_cols > 1:
                first_w = Inches(1.80)
                rest_w = (Inches(6.70) - first_w) / (num_cols - 1)
                col_widths = [first_w] + [rest_w] * (num_cols - 1)
            else:
                col_widths = [Inches(6.70)]

        tbl = self.doc.add_table(rows=len(raw_rows), cols=num_cols)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False

        # Set fixed layout and 6.70 in total width (9648 dxa)
        tblPr = tbl._tbl.tblPr
        tblPr.append(parse_xml(r'<w:tblW xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:w="9648" w:type="dxa"/>'))
        tblPr.append(parse_xml(r'<w:tblLayout xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:type="fixed"/>'))

        for c_idx, w in enumerate(col_widths):
            if c_idx < len(tbl.columns):
                tbl.columns[c_idx].width = w

        # Borders: IEEE Booktabs
        bdr_xml = parse_xml(r'''<w:tblBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/>
            <w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/>
            <w:left w:val="none"/><w:right w:val="none"/>
            <w:insideH w:val="none"/><w:insideV w:val="none"/>
        </w:tblBorders>''')
        tblPr.append(bdr_xml)

        # Style Rows
        for r_idx, row_data in enumerate(raw_rows):
            w_row = tbl.rows[r_idx]
            trPr = w_row._tr.get_or_add_trPr()
            trPr.append(parse_xml(r'<w:cantSplit xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'))

            # Repeat header row across pages
            if r_idx == 0:
                trPr.append(parse_xml(r'<w:tblHeader xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'))

            for c_idx, val in enumerate(row_data):
                cell = w_row.cells[c_idx]
                if col_widths and c_idx < len(col_widths):
                    cell.width = col_widths[c_idx]
                    tcPr = cell._tc.get_or_add_tcPr()
                    tcW = parse_xml(f'<w:tcW xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:w="{int(col_widths[c_idx].inches * 1440)}" w:type="dxa"/>')
                    tcPr.append(tcW)

                set_cell_margins(cell, top=35, bottom=35, left=cell_pad_lr, right=cell_pad_lr)

                # Set mid-rule line below header row
                if r_idx == 0:
                    tcPr = cell._tc.get_or_add_tcPr()
                    tcBorders = parse_xml(r'<w:tcBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/></w:tcBorders>')
                    tcPr.append(tcBorders)

                p = cell.paragraphs[0]
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.05

                # Alignment: Right-align numbers, Left-align text
                clean_val = val.strip()
                is_numeric = bool(re.match(r"^[\+\-]?\d+(\.\d+)?%?x?\$?b?p?s?$", clean_val))
                if (align_right_cols and c_idx in align_right_cols) or (r_idx > 0 and is_numeric and c_idx > 0):
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

                clean_txt = clean_val.replace("**", "").replace("*", "").replace("`", "")
                r = p.add_run(clean_txt)
                r.font.name = "Times New Roman"
                r.font.size = font_size
                r.font.color.rgb = RGBColor(0, 0, 0)
                if r_idx == 0:
                    r.font.bold = True

        # Footnotes (pure black italic)
        for fn in footnotes:
            p_fn = self.doc.add_paragraph()
            p_fn.paragraph_format.space_before = Pt(2)
            p_fn.paragraph_format.space_after = Pt(4)
            r_fn = p_fn.add_run(fn)
            r_fn.font.name = "Times New Roman"
            r_fn.font.size = Pt(7.5)
            r_fn.font.italic = True
            r_fn.font.color.rgb = RGBColor(0, 0, 0)

    def add_figure(self, filename: str, caption_text: str):
        """Embed centered 300 DPI research figure with formal IEEE caption."""
        img_path = FIGURES_DIR / filename
        if not img_path.exists():
            print(f"Warning: Figure {img_path} not found.")
            return

        p_img = self.doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_before = Pt(8)
        p_img.paragraph_format.space_after = Pt(3)
        p_img.paragraph_format.keep_with_next = True
        p_img.add_run().add_picture(str(img_path), width=Inches(5.8))

        p_cap = self.doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_before = Pt(2)
        p_cap.paragraph_format.space_after = Pt(8)
        r_cap = p_cap.add_run(caption_text)
        r_cap.font.name = "Times New Roman"
        r_cap.font.size = Pt(8.0)
        r_cap.font.color.rgb = RGBColor(0, 0, 0)

    def compile(self, page_map: dict = None):
        """Master compile routine: parses report/REPORT.md into report/REPORT.docx."""
        print(f"=== Reading Markdown from {REPORT_MD} ===")
        with open(REPORT_MD, "r", encoding="utf-8") as f:
            content = f.read()

        print("=== Building Front Matter Block ===")
        self.add_title_block(page_map=page_map)

        sections = content.split("\\newpage")

        # Map of figure references to files and formal IEEE captions
        fig_map = {
            "fig1_rating_distribution": ("fig1_rating_distribution.png", "Fig. 1. S&P Credit Rating Distribution Across Longitudinal Corporate Research Panel (2000–2025)."),
            "fig2_macro_series": ("fig2_macro_series.png", "Fig. 2. Historical Trajectories of Macroeconomic Regressors and Monetary Policy Cycles (2000–2025)."),
            "fig3_shadow_rating_gap": ("fig3_shadow_rating_gap.png", "Fig. 3. Historical Point-in-Time Latent Shadow Rating vs S&P Published Rating Trajectory."),
            "fig4_migration_matrix": ("fig4_migration_matrix.png", "Fig. 4. 12-Month Multi-State Credit Rating Migration Probability Heatmap Across Credit States."),
            "fig5_roc_pr_curves": ("fig5_roc_pr_curves.png", "Fig. 5. Out-of-Sample ROC and Precision-Recall Curves on Embargoed Test Window (2020–2025)."),
            "fig6_lead_time_distribution": ("fig6_lead_time_distribution.png", "Fig. 6. Distribution of Early-Warning Advance Notice: Quantitative Model Alert vs S&P CreditWatch."),
            "fig7_macro_sensitivity_interactions": ("fig7_macro_sensitivity_interactions.png", "Fig. 7. Marginal Macro Sensitivity Interactions with Corporate Leverage and Interest Coverage."),
            "fig8_sector_vulnerability_heatmap": ("fig8_sector_vulnerability_heatmap.png", "Fig. 8. Fama-French 12 Sector Stress Vulnerability Heatmap Under Monetary Policy Tightening."),
            "fig9_var_scenarios": ("fig9_var_scenarios.png", "Fig. 9. Conditional VAR Scenario Trajectories and Coherent Macroeconomic Stress Test Paths."),
            "fig10_placebo_diagnostics": ("fig10_placebo_diagnostics.png", "Fig. 10. Placebo Permutation Null Distribution and Target-Shuffled Negative Control Diagnostics.")
        }

        is_first_h1 = True

        for sec_idx, sec in enumerate(sections):
            if sec_idx == 0:
                # Front matter already rendered
                continue

            lines = sec.strip().split("\n")
            in_code_block = False
            code_lines = []
            in_eq_block = False
            eq_lines = []

            for line in lines:
                l_str = line.strip()

                if in_code_block:
                    if l_str.startswith("```"):
                        self.add_table_block("\n".join(code_lines))
                        code_lines = []
                        in_code_block = False
                    else:
                        code_lines.append(line)
                    continue

                if l_str.startswith("```"):
                    in_code_block = True
                    continue

                if in_eq_block:
                    eq_lines.append(l_str)
                    if "$$" in l_str:
                        self.add_equation_omml(" ".join(eq_lines))
                        eq_lines = []
                        in_eq_block = False
                    continue

                if not l_str:
                    continue

                # Image detection
                img_m = re.search(r"!\[(.*?)\]\((.*?)\)", l_str)
                if img_m:
                    img_path = img_m.group(2)
                    matched_fig = False
                    for f_key, (f_name, f_cap) in fig_map.items():
                        if f_key in img_path:
                            self.add_figure(f_name, f_cap)
                            matched_fig = True
                            break
                    if not matched_fig:
                        base = Path(img_path).name
                        self.add_figure(base, f"Fig. Research visualization: {img_m.group(1)}.")
                    continue

                # Heading detection (new section starts on new page)
                if l_str.startswith("# "):
                    self.add_heading_1(l_str[2:], is_first=is_first_h1)
                    is_first_h1 = False
                elif l_str.startswith("## "):
                    self.add_heading_2(l_str[3:])
                elif l_str.startswith("### "):
                    self.add_heading_3(l_str[4:])
                elif l_str.startswith("$$"):
                    if l_str.endswith("$$") and len(l_str) > 2 and l_str[2:].find("$$") != -1:
                        self.add_equation_omml(l_str)
                    else:
                        in_eq_block = True
                        eq_lines = [l_str]
                elif l_str.startswith("---"):
                    continue
                else:
                    self.add_paragraph_formatted(l_str)

        print(f"=== Saving DOCX to {OUTPUT_DOCX} ===")
        self.doc.save(str(OUTPUT_DOCX))
        print("DOCX successfully generated in report/.")


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path):
    """Automate Microsoft Word via COM to export publication-grade PDF."""
    print("=== Automating Microsoft Word COM for PDF Export ===")
    word = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(docx_path.resolve()))

        # Update all dynamic fields (page numbers)
        try:
            doc.Fields.Update()
        except:
            pass

        # 17 = wdExportFormatPDF, 0 = wdExportOptimizeForPrint
        doc.ExportAsFixedFormat(
            OutputFileName=str(pdf_path.resolve()),
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            CreateBookmarks=1,
            DocStructureTags=True
        )
        doc.Close(False)
        print(f"PDF successfully exported to: {pdf_path}")
    finally:
        if word:
            word.Quit()


def extract_section_pages_from_pdf(pdf_path: Path) -> dict:
    """Inspect the PDF using pypdf to determine the exact page where each section heading appears."""
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))

    targets = [
        ("Section I", ["I. INTRODUCTION & PROBLEM FORMULATION", "I. INTRODUCTION"]),
        ("Section II", ["II. THEORETICAL FOUNDATION & ECONOMETRIC METHODOLOGY", "II. THEORETICAL FOUNDATION"]),
        ("Section III", ["III. DATA PIPELINE, PANEL CONSTRUCTION & LEAKAGE SAFEGUARDS", "III. DATA PIPELINE"]),
        ("Section IV", ["IV. ECONOMETRIC FINDINGS & MACRO SENSITIVITY INTERACTIONS", "IV. ECONOMETRIC FINDINGS"]),
        ("Section V", ["V. FALLEN-ANGEL EARLY WARNING & OUT-OF-SAMPLE VALIDATION", "V. FALLEN-ANGEL EARLY WARNING"]),
        ("Section VI", ["VI. MACRO STRESS TESTING & SECTOR VULNERABILITY ANALYSIS", "VI. MACRO STRESS TESTING"]),
        ("Section VII", ["VII. ROBUSTNESS CHECKS, PLACEBO CONTROLS & SENSITIVITY ANALYSIS", "VII. ROBUSTNESS CHECKS"]),
        ("Section VIII", ["VIII. RISK MANAGEMENT IMPLICATIONS & REGULATORY COMPLIANCE", "VIII. RISK MANAGEMENT"]),
        ("Section IX", ["IX. CONCLUSION & CONCLUDING REMARKS", "IX. CONCLUSION"]),
        ("Appendix", ["APPENDIX: MATHEMATICAL DERIVATIONS & PROOFS", "APPENDIX: MATHEMATICAL DERIVATIONS"]),
        ("References", ["REFERENCES"]),
    ]

    page_map = {}
    for tag, phrases in targets:
        for page_idx, page in enumerate(reader.pages):
            if page_idx == 0:
                continue  # skip cover / TOC page
            txt = page.extract_text() or ""
            if any(p.upper() in txt.upper() for p in phrases):
                page_map[tag] = page_idx + 1  # 1-indexed
                break

    return page_map


def parse_and_compile_report():
    """Master pipeline callable to generate DOCX and PDF with exact synchronized page numbers in TOC."""
    print("=== Pass 1: Generating initial document to calibrate page layout ===")
    builder = WordReportBuilder()
    builder.compile(page_map=None)
    convert_docx_to_pdf(OUTPUT_DOCX, OUTPUT_PDF)

    print("=== Detecting Exact Page Locations in Generated PDF ===")
    actual_pages = extract_section_pages_from_pdf(OUTPUT_PDF)
    print(f"Discovered actual section page locations: {actual_pages}")

    print("=== Pass 2: Re-generating document with calibrated TOC page numbers ===")
    builder_v2 = WordReportBuilder()
    builder_v2.compile(page_map=actual_pages)
    convert_docx_to_pdf(OUTPUT_DOCX, OUTPUT_PDF)

    from pypdf import PdfReader
    final_pages = extract_section_pages_from_pdf(OUTPUT_PDF)
    print(f"=== Final Verified Section Page Locations: {final_pages} ===")
    print(f"Report successfully compiled in {REPORT_DIR}! Total pages: {len(PdfReader(str(OUTPUT_PDF)).pages)}")


if __name__ == "__main__":
    parse_and_compile_report()
