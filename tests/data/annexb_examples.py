"""Appendix B's own examples (JACoW style guide v2026-02-23), as each must come out.

Three of the printed examples have typos the layout itself rules out, corrected
here: "Aug.-Sep" ([3]), "Aug" ([4]) and "May." ([10]) are written "Aug.-Sep.",
"Aug." and "May"; [5] has its comma after "China". [12] writes "Optics Express"
in full, but Annex C abbreviates it "Opt. Express". [29] and [32] use
placeholders ("Country", "<Patent Authority and No.>"), replaced by real ones.
"""

EXAMPLES = [
    ("conference", "A. Alpha, “Novel techniques for a future TeV electron accelerator”, in Proc. IPAC’23, Venice, Italy, May 2023, pp. 57-59. doi:10.18429/JACoW-IPAC2023-PAPERID"),
    ("conference", "A. Alpha and B. T. Beta, “An overview of modern control systems”, in Proc. ICALEPCS’23, Cape Town, South Africa, Oct. 2023, pp. 57-59. doi:10.18429/JACoW-ICALEPCS2023-PAPERID"),
    ("conference", "A. Alpha, B. T. Beta, and J.-P. Gamma, “Compact light sources”, in Proc. FLS’23, Lucerne, Switzerland, Aug.-Sep. 2023, pp. 57-59. doi:10.18429/JACoW-FLS2023-PAPERID"),
    ("conference", "A. Alpha et al., “Novel techniques for future TeV electron accelerators”, in Proc. LINAC’24, Chicago, IL, USA, Aug. 2024, pp. 57-59. doi:10.18429/JACoW-LINAC2024-PAPERID"),
    ("conference", "A. Alpha, B. T. Beta, et al., “Status of cyclotrons around the world”, in Proc. Cyclotrons’22, Beijing, China, Dec. 2022, pp. 57-59. doi:10.18429/JACoW-CYCLOTRONS2022-PAPERID"),
    ("conference_unpublished", "A. Alpha, “An interesting talk but paper not submitted”, presented at IPAC’14, Dresden, Germany, Jun. 2014, paper MOP057, unpublished."),
    ("conference_current", "A. Alpha and B. T. Beta, “Title of talk or poster presented at this conference”, presented at IPAC’25, Taipei, Taiwan, Jun. 2025, paper MOAB01, this conference."),
    ("journal", "A. Alpha et al., “Title of paper published in journal”, Phys. Rev. Lett., vol. 114, no. 5, p. 050511, Feb. 2014. doi:10.1103/PhysRevLett.114.050511"),
    ("journal", "A. Alpha, “New techniques in laser wakefield accelerators”, Phys. Rev. Accel. Beams, vol. 22, p. 014601, Jan. 2019. doi:10.1103/PhysRevAccelBeams.22.014601"),
    ("journal", "A. Alpha, B. Beta, C. Gamma, D. Delta, E. Epsilon, and Z. Zeta, “Exotic beams”, Phys. Rev. Spec. Top. Accel. Beams, vol. 1, p. 013501, May 1998. doi:10.1103/PhysRevSTAB.1.013501"),
    ("journal", "A. Alpha et al., “Low dose irradiation impact on modern silicon detectors”, Nucl. Instrum. Methods Phys. Res. A, vol. 773, pp. 1-7, 2015. doi:10.1016/j.nima.2014.11.022"),
    ("journal", "A. Alpha, B. Beta, and C. Gamma, “Temporal correlations of x-ray free electron lasers”, Opt. Express, vol. 33, no. 8, pp. 17884-17885, 2012. doi:10.1364/OE.564805"),
    ("accepted", "J. B. Good, “Title of paper accepted for publication”, Phys. Rev. Lett., to be published."),
    ("submitted", "G. D. Read, “Title of paper”, submitted for publication."),
    ("arxiv", "A. Alpha, “Title of arXiv preprint”, Jan. 2025. doi:10.48550/arXiv.2501.10602"),
    ("online", "JACoW, https://www.jacow.org"),
    ("online", "EPICS, https://www.epics-controls.org"),
    ("online", "Principal Component Analysis, https://en.wikipedia.org/wiki/Principal_component_analysis"),
    ("book_chapter", "A. Alpha and B. Beta, “Title of chapter in the book”, in Title of Book, R. Mars, Ed. New York, NY, USA: Wiley, 1994, pp. 42-48."),
    ("book", "A. Alpha, Title of Book. Cambridge, MA, USA: MIT Press, 1986."),
    ("report", "A. Alpha et al., “Title of report”, CERN, Geneva, Switzerland, Rep. CERN-2012-333, Oct. 2012."),
    ("report", "A. Alpha, B. Beta, C. Gamma, D. Delta, E. Epsilon, and Z. Zeta, “Title of report”, SLAC National Accelerator Laboratory, Menlo Park, CA, USA, Rep. SLAC-REP-474, May 1996."),
    ("technical_report", "SLS-2 Conceptional Design Report, A. Streun, Ed., Paul Scherrer Institute, Villigen, Switzerland, Rep. 17-03, Dec. 2017. https://www.dora.lib4ri.ch/psi/item/psi:34977"),
    ("technical_report", "Advanced Photon Source Upgrade Project Final Design Report, Argonne National Laboratory, Lemont, IL, USA, Rep. APSU-2.01-RPT-003, May 2019. https://publications.anl.gov/anlpubs/2019/07/153666.pdf"),
    ("technical_report", "SwissFEL Conceptual Design Report, 2nd ed., R. Ganter, Ed., Paul Scherrer Institute, Villigen, Switzerland, Rep. 10-04, Apr. 2012. https://www.dora.lib4ri.ch/psi/item/psi:41664"),
    ("thesis", "A. Student, “Title of thesis”, Ph.D. thesis, Phys. Dept., Karlsruher Institut für Technologie, Karlsruhe, Germany, 2014."),
    ("handbook", "Name of Handbook, 2nd ed., Name of Company, Germany, Apr. 2024, pp. 34-52, http://www.xyz.com/etc"),
    ("handbook", "Motorola Semiconductor Handbook, Motorola Semiconductor Products Inc., Phoenix, AZ, USA, Nov. 2021, https://www.motorola.com/etc"),
    ("manual", "IEEE Editorial Style Manual for Authors, IEEE Periodicals, Piscataway, NJ, USA, Mar. 2025. https://docs.google.com/document/d/1OalFYqVfxKKMelF79U3B93SjmIEiTnJC12wPJrKeSDM/"),
    ("patent", "A. N. Inventor, “Title of patent”, U.S. Patent 9 123 456, Jan. 20, 2016."),
    ("patent", "A. N. Inventor, “Title of patent”, U.S. Patent, patent pending."),
    ("unpublished", "P. Neptune, “Title of paper”, unpublished."),
    ("private", "P. Uranus, private communication, Jun. 2015."),
]
