import { ShieldCheck } from 'lucide-react';
import LegalLayout, { Section, P, H, UL, LI, B, Mail } from '../components/LegalLayout';

/**
 * Privacy Policy for the Auditable Filing-QA research demo. Written to reflect
 * what the app *actually* does: anonymous PostHog usage analytics, a little
 * localStorage, the questions you type, and optional feedback — no accounts,
 * no marketing. Operator-neutral ("we"), jurisdiction-neutral.
 */
export default function Privacy() {
  return (
    <LegalLayout
      title="Privacy Policy"
      subtitle="What this research demo collects, why, and your choices."
      updated="27 June 2026"
      icon={<ShieldCheck />}
      otherDoc={{ label: 'Terms of Use', path: '/terms' }}
    >
      <Section n="1" title="Who we are">
        <P>
          Auditable Filing-QA (the <B>“Service”</B>) is a personal, non-commercial research and
          educational project that lets you ask questions about public U.S. SEC filings and returns
          AI-generated answers with source citations. In this policy, <B>“we,” “us,”</B> and{' '}
          <B>“the operator”</B> refer to the individual who builds and runs the Service. You can
          reach us at <Mail />.
        </P>
        <P>
          We try to collect as little as possible. There are no user accounts, and we do not ask you
          to provide your name, email, or any other identifying information to use the Service.
        </P>
      </Section>

      <Section n="2" title="Information we collect">
        <H>Information you provide</H>
        <UL>
          <LI>
            <B>Questions you submit.</B> The text of the queries you type into the chat are sent to
            our backend so the system can retrieve filings and generate an answer.
          </LI>
          <LI>
            <B>Feedback.</B> If you rate an answer (thumbs up/down) or leave a comment, we store that
            rating and comment to help improve answer quality.
          </LI>
          <LI>
            <B>Survey responses.</B> If you choose to complete the optional preference (conjoint)
            survey, we store your selections.
          </LI>
          <LI>
            <B>Anything you send us.</B> If you email us, we keep your message and address to reply.
          </LI>
        </UL>

        <H>Information collected automatically</H>
        <UL>
          <LI>
            <B>Usage analytics.</B> We use PostHog to record anonymous product-analytics events —
            for example page views, which features you open, and similar in-app actions — together
            with technical details your browser sends, such as browser/device type, screen size,
            approximate location inferred from your IP address, and the page that referred you.
          </LI>
          <LI>
            <B>Shared-link attribution.</B> If you arrive via a tracking or referral link (for
            example a short link with a <code className="text-secondary/80">ref</code> or{' '}
            <code className="text-secondary/80">utm_*</code> tag), we record that the link was opened,
            so we can understand which shared links generate visits.
          </LI>
          <LI>
            <B>Local storage.</B> We keep a few small values in your browser’s local storage — for
            example whether you have acknowledged the disclaimer, whether you have seen a guided
            tour, and your saved survey preferences — so the Service behaves sensibly on repeat
            visits. These stay on your device and can be cleared at any time.
          </LI>
        </UL>
        <P>
          PostHog is configured to create person profiles for <B>identified users only</B>. Because
          the Service does not identify you, your analytics events are not tied to a named profile.
        </P>
      </Section>

      <Section n="3" title="How we use information">
        <UL>
          <LI>To operate the Service and generate answers to your questions.</LI>
          <LI>To understand how the Service is used and improve its features and answer quality.</LI>
          <LI>To diagnose problems, monitor reliability, and prevent abuse or misuse.</LI>
          <LI>To respond to you if you contact us.</LI>
        </UL>
        <P>
          We do <B>not</B> sell your information, use it for advertising, or use it to build profiles
          about you across other websites.
        </P>
      </Section>

      <Section n="4" title="Cookies and similar technologies">
        <P>
          We do not use advertising or cross-site tracking cookies. Our analytics provider (PostHog)
          may set first-party cookies or use your browser’s local storage to measure usage and
          distinguish repeat visits. As described above, we also keep a few small values directly in
          your browser’s local storage for the app to function (disclaimer acknowledgement, tour
          state, saved preferences). You can block or clear these through your browser settings or a
          tracker blocker; the Service still works.
        </P>
      </Section>

      <Section n="5" title="Third-party processors">
        <P>The Service relies on a small number of providers to function. Each processes data under
          its own terms and privacy policy:</P>
        <UL>
          <LI>
            <B>Hosting.</B> The application runs on a third-party cloud platform (Hugging Face
            Spaces), which processes the network requests needed to serve the app.
          </LI>
          <LI>
            <B>Analytics.</B> PostHog processes the anonymous usage events described above.
          </LI>
          <LI>
            <B>AI model providers.</B> To generate and verify an answer, the text you submit and the
            relevant filing excerpts may be sent to a third-party AI/LLM provider — depending on
            configuration, this may be DeepSeek, OpenAI, Anthropic, or Xiaomi MiMo. Please don’t
            include personal or sensitive information in your questions.
          </LI>
          <LI>
            <B>Observability.</B> We may use LangSmith to trace and debug request pipelines, which can
            include the content of a query and the system’s intermediate steps.
          </LI>
          <LI>
            <B>Market data.</B> Polygon.io is used for supplementary company/market data and
            cross-checks.
          </LI>
          <LI>
            <B>Source data.</B> Filing content comes from public records on SEC EDGAR; we don’t send
            your personal data to EDGAR.
          </LI>
        </UL>
      </Section>

      <Section n="6" title="Data retention">
        <P>
          We keep submitted questions, feedback, and survey responses only as long as useful for
          operating and improving the Service, and analytics data for a limited period consistent
          with our analytics provider’s defaults. Because this is a demo without persistent
          server-side storage, some operational data may be retained only transiently or in periodic
          snapshots used to evaluate the system. You can ask us to delete data associated with you by
          emailing <Mail /> — though note that anonymous analytics generally cannot be linked back to
          a specific person.
        </P>
      </Section>

      <Section n="7" title="Your choices and rights">
        <UL>
          <LI>
            <B>Local storage.</B> You can clear the values we store on your device through your
            browser settings at any time.
          </LI>
          <LI>
            <B>Analytics.</B> You can use your browser’s privacy controls or a tracker blocker to
            limit analytics collection; the Service still works.
          </LI>
          <LI>
            <B>Access / deletion.</B> Subject to applicable law, you may request access to, or
            deletion of, information that identifies you by contacting <Mail />.
          </LI>
        </UL>
      </Section>

      <Section n="8" title="Children">
        <P>
          The Service is not directed to children and is intended for an adult, general audience. We
          do not knowingly collect information from children.
        </P>
      </Section>

      <Section n="9" title="International users">
        <P>
          The Service may be operated and its providers located in countries other than yours. By
          using the Service, you understand that your information may be processed in those locations,
          which may have different data-protection rules than your own.
        </P>
      </Section>

      <Section n="10" title="Security">
        <P>
          We take reasonable measures to protect the limited information handled by the Service.
          However, no method of transmission or storage is completely secure, and we cannot guarantee
          absolute security.
        </P>
      </Section>

      <Section n="11" title="Changes to this policy">
        <P>
          We may update this policy from time to time. When we do, we’ll revise the “Last updated”
          date above. Continued use of the Service after a change means you accept the updated policy.
        </P>
      </Section>

      <Section n="12" title="Contact">
        <P>
          Questions about this policy or your information? Email <Mail />.
        </P>
      </Section>
    </LegalLayout>
  );
}
