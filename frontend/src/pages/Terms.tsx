import { Scale } from 'lucide-react';
import LegalLayout, { Section, P, H, UL, LI, B, Mail } from '../components/LegalLayout';

/**
 * Terms of Use for the Auditable Filing-QA research demo. The load-bearing
 * clauses are the "not investment advice" and "no warranty / AS IS" sections,
 * which mirror the in-app Disclaimer. Operator-neutral ("we"),
 * jurisdiction-neutral (no specific governing-law venue named).
 */
export default function Terms() {
  return (
    <LegalLayout
      title="Terms of Use"
      subtitle="The rules for using this research demo. Please read the disclaimer carefully."
      updated="27 June 2026"
      icon={<Scale />}
      otherDoc={{ label: 'Privacy Policy', path: '/privacy' }}
    >
      <Section n="1" title="Acceptance of these terms">
        <P>
          Auditable Filing-QA (the <B>“Service”</B>) is a personal, non-commercial research and
          educational project operated by an individual (<B>“we,” “us,” “the operator”</B>). By
          accessing or using the Service, you agree to these Terms of Use. If you do not agree, please
          do not use the Service.
        </P>
      </Section>

      <Section n="2" title="What the Service is">
        <P>
          The Service lets you ask questions about public U.S. SEC filings and returns AI-generated
          answers with citations to source documents. It is a <B>demonstration and research tool</B>,
          provided free of charge, and may be incomplete, experimental, or changed or withdrawn at any
          time without notice.
        </P>
      </Section>

      <Section n="3" title="Not investment, financial, or professional advice">
        <P>In plain terms:</P>
        <UL>
          <LI>Information is for <B>educational and demonstration purposes</B>.</LI>
          <LI>It is <B>not financial, investment, legal, or tax advice</B>.</LI>
          <LI>AI-generated responses <B>may contain errors</B>.</LI>
          <LI>You should <B>verify information against the original SEC filings</B>.</LI>
          <LI>Use of the application is <B>at your own risk</B>.</LI>
        </UL>
        <P>
          Nothing the Service produces is a recommendation or an offer or solicitation to buy or sell
          any security or financial instrument. Always consult a licensed professional before making
          any decision. Please do your own due diligence.
        </P>
      </Section>

      <Section n="4" title="Independent personal project">
        <P>
          This application is an <B>independent personal project</B>, developed on the operator’s own
          time using the operator’s own resources. The views, code, and demonstrations are the
          operator’s own and <B>do not represent the views of any current or former employer</B>. Any
          company names or filings referenced are publicly available and used <B>solely for
          demonstration and educational purposes</B>.
        </P>
      </Section>

      <Section n="5" title="Acceptable use">
        <P>You agree not to:</P>
        <UL>
          <LI>Use the Service for any unlawful purpose or in violation of any applicable law.</LI>
          <LI>
            Present the Service’s output to others as professional, financial, or investment advice.
          </LI>
          <LI>
            Attempt to disrupt, overload, scrape at scale, probe, or circumvent the security or rate
            limits of the Service or its infrastructure.
          </LI>
          <LI>
            Reverse engineer, decompile, or attempt to extract source code or model weights, except
            where such restriction is prohibited by law.
          </LI>
          <LI>
            Submit content you are not entitled to share, or include personal, confidential, or
            sensitive information in your questions.
          </LI>
          <LI>Use the Service to develop a competing product or to train other models.</LI>
        </UL>
      </Section>

      <Section n="6" title="Intellectual property">
        <H>Filings and source data</H>
        <P>
          The underlying filings are public records obtained from SEC EDGAR. Rights in that content
          belong to the respective filers or are in the public domain, and your use of it is subject
          to any applicable rules of the source.
        </P>
        <H>The application</H>
        <P>
          The Service’s software, design, and presentation are owned by the operator. We grant you a
          limited, personal, non-exclusive, revocable licence to use the Service for its intended
          research and educational purpose. We make no ownership claim over the source filings.
        </P>
      </Section>

      <Section n="7" title="Third-party services and content">
        <P>
          The Service depends on third-party providers (hosting, analytics, and AI model providers)
          and links to or surfaces third-party content such as SEC filings. We do not control and are
          not responsible for third-party services or content, and your use of them is governed by
          their own terms.
        </P>
      </Section>

      <Section n="8" title="No warranties">
        <P>
          The Service is provided <B>“as is” and “as available,” without warranties of any kind</B>,
          whether express or implied, including any implied warranties of merchantability, fitness for
          a particular purpose, accuracy, and non-infringement. We do not warrant that the Service will
          be uninterrupted, error-free, secure, or that any answer it produces is accurate, current, or
          complete.
        </P>
      </Section>

      <Section n="9" title="Limitation of liability">
        <P>
          To the fullest extent permitted by law, the operator will not be liable for any indirect,
          incidental, special, consequential, or punitive damages, or for any loss of profits,
          investments, data, or goodwill, arising out of or relating to your use of (or inability to
          use) the Service or any reliance on its output — even if advised of the possibility of such
          damages. Because the Service is provided free of charge for research, our total aggregate
          liability for any claim relating to the Service is limited to the greater of the amount you
          paid to use it (which is zero) or the minimum amount permitted by applicable law.
        </P>
      </Section>

      <Section n="10" title="Indemnification">
        <P>
          You agree to indemnify and hold the operator harmless from any claims, losses, or expenses
          arising out of your misuse of the Service or your violation of these terms or of any
          applicable law or third-party right.
        </P>
      </Section>

      <Section n="11" title="Availability and changes to the Service">
        <P>
          The Service is offered on a best-effort basis and may be modified, suspended, or
          discontinued at any time, in whole or in part, without notice or liability.
        </P>
      </Section>

      <Section n="12" title="Changes to these terms">
        <P>
          We may revise these terms from time to time. Material changes will be reflected by updating
          the “Last updated” date above. Your continued use of the Service after a change means you
          accept the revised terms.
        </P>
      </Section>

      <Section n="13" title="Governing law and disputes">
        <P>
          These terms are governed by the applicable laws where the operator resides. Where required
          by mandatory consumer-protection law, nothing in these terms limits rights that cannot be
          waived. The parties will seek to resolve any dispute informally and in good faith before
          pursuing other remedies.
        </P>
      </Section>

      <Section n="14" title="Contact">
        <P>
          Questions about these terms? Email <Mail />.
        </P>
      </Section>
    </LegalLayout>
  );
}
