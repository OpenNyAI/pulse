from datetime import datetime
import json
import re
from dotenv import load_dotenv
import uuid
from enum import Enum
import requests
import logging

from transitions import Machine
import os
import sys
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append("..")
from lib.data_models import MessageType, FSMOutput, OptionsListType, UploadFile
from llm import llm, sm, um

# enum
load_dotenv("../.env-dev")
magic_string = os.getenv("JB_MAGIC_STRING")

logging.basicConfig()
logger = logging.getLogger("flow")
logger.setLevel(logging.INFO)


class Status(Enum):
    WAIT_FOR_ME = 0
    WAIT_FOR_USER_INPUT = 1
    MOVE_FORWARD = 2
    WAIT_FOR_CALLBACK = 3


class FSM:
    states = [
        "zero",
        "select_language",
        "select_options_main",
        "udyam_check",
        "give_udyam_info",
        "ask_for_udyam_question",
        "fetch_udyam_answer",
        "generate_udyam_response",
        "ask_for_another_udyam_question",
        "ask_details",
        "ask_investment",
        "process_investment_options",
        "ask_turnover",
        "process_turnover_options",
        "evaluate_category",
        "ask_for_sector_lending",
        "process_sector_lending_options",
        "select_business_type",
        "process_business_type_options",
        "sector_lending_eligible",
        "sector_lending_not_eligible",
        "requirements",
        "ask_aadhar",
        "ask_pan",
        "ask_gst_number",
        "ask_prev",
        "evaluate_eligibility",
        "ask_for_udyam_assistance",
        "fetch_udyam_advisors",
        "select_udyam_advisor",
        "process_udyam_advisor_options",
        "confirm_udyam_advisor",
        "process_udyam_advisor_options",
        "udyam_registration_form",
        "process_udyam_form_options",
        "ask_for_gst_assistance",
        "gst_registration",
        "fetch_advisors",
        "select_advisor",
        "process_select_advisor_options",
        "confirm_advisor",
        "process_confirm_advisor_options",
        "ask_name",
        "ask_business_name",
        "select_business_category",
        "ask_documents",
        "submit_documents",
        "process_documents_options",
        "select_lawyer_slot",
        "process_slot_options",
        "send_link",
        "odr_know_more",
        "odr_know_more",
        "odr_info",
        "explore_odr",
        "fetch_odr_providers",
        "select_odr_provider",
        "selected_provider_details",
        "fix_provider",
        "collect_details",
        "form_filled",
        "consent_form",
        "confirm_odr_provider",
        "fix_selected_provider",
        "send_link_odr",
        "ask_further_assistance",
        "end",
    ]

    status = Status.WAIT_FOR_ME
    variables = dict()

    def _save_state(self):
        return self.state, self.variables

    def _restore_state(self, state, variables):
        self.state = state
        self.variables = variables
        self.status = Status.WAIT_FOR_ME

    def process_input_or_callback(self, input):
        self.input = input

        while self.state != "end":
            self.next()
            if self.status == Status.MOVE_FORWARD:
                continue
            else:
                break

    def __init__(self, cb: callable, generate_reference_id: callable = None):
        self.cb = cb
        self.generate_reference_id = generate_reference_id

        transitions = [
            {"trigger": "next", "source": FSM.states[i], "dest": FSM.states[i + 1]}
            for i in range(len(FSM.states) - 1)
        ]

        FSM.states.append("ask_for_question")
        FSM.states.append("fetch_answer")
        FSM.states.append("generate_response")
        FSM.states.append("ask_for_another_question")
        FSM.states.append("process_query")
        FSM.states.append("generate_query_response")

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_assistance",
                "dest": "end",
                "conditions": "if_assistance_not_required",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_language",
                "dest": "select_options_main",
                "conditions": "if_dialog_contains_selected_language",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_options_main",
                "dest": "ask_for_question",
                "conditions": "is_know_more",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_question",
                "dest": "fetch_answer",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "fetch_answer",
                "dest": "generate_response",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "generate_response",
                "dest": "ask_for_another_question",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_another_question",
                "dest": "ask_for_question",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_another_question",
                "dest": "ask_further_assistance",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_option_main",
                "dest": "udyam_check",
                "conditions": "is_udyam_eligibility",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "udyam_check",
                "dest": "give_udyam_info",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "udyam_check",
                "dest": "ask_details",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_another_udyam_question",
                "dest": "ask_for_udyam_question",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_another_udyam_question",
                "dest": "ask_details",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_sector_lending",
                "dest": "ask_further_assistance",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_business_type",
                "dest": "sector_lending_eligible",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_business_type",
                "dest": "sector_lending_not_eligible",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "evaluate_eligibility",
                "dest": "ask_for_udyam_assistance",
                "conditions": "is_business_eligible",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "evaluate_eligibility",
                "dest": "ask_for_gst_assistance",
                "conditions": "is_business_not_eligible",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "sector_lending_eligible",
                "dest": "requirements",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "sector_lending_eligible",
                "dest": "ask_further_assistance",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "sector_lending_not_eligible",
                "dest": "ask_further_assistance",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_udyam_assistance",
                "dest": "fetch_udyam_advisors",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_udyam_advisor",
                "dest": "ask_to_select_udyam_advisor_again",
                "conditions": "is_not_valid_udyam_advisor",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_to_select_udyam_advisor_again",
                "dest": "select_udyam_advisor",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "confirm_udyam_advisor",
                "dest": "udyam_registration_form",
                "conditions": "is_confirmed",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "udyam_registration_form",
                "dest": "select_lawyer_slot",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "confirm_udyam_advisor",
                "dest": "ask_further_assistance",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_gst_assistance",
                "dest": "fetch_advisors",
                "conditions": ["is_confirmed"],
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_gst_assistance",
                "dest": "ask_further_assistance",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_gst_assistance",
                "dest": "ask_further_assistance",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_options_main",
                "dest": "fetch_advisors",
                "conditions": "is_consult_advisor",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_advisor",
                "dest": "ask_to_select_advisor_again",
                "conditions": "is_not_valid_advisor",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_to_select_advisor_again",
                "dest": "select_advisor",
            }
        )

        transitions.append(
            {"trigger": "next", "source": "confirm_advisor", "dest": "send_link"}
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "confirm_advisor",
                "dest": "ask_name",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "send_link",
                "dest": "ask_further_assistance",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_further_assistance",
                "dest": "select_options_main",
                "conditions": "if_assistance_required",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_further_assistance",
                "dest": "end",
                "conditions": "if_assistance_not_required",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_options_main",
                "dest": "gst_registration",
                "conditions": "if_gst_registration",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_options_main",
                "dest": "fetch_udyam_advisors",
                "conditions": "is_udyam_registration",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_query",
                "dest": "generate_query_response",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "evaluate_category",
                "dest": "ask_investment",
                "conditions": "is_invalid_category",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_investment_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "ask_investment",
                "conditions": "is_investment_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_turnover_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "ask_turnover",
                "conditions": "is_turnover_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_sector_lending_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "ask_for_sector_lending",
                "conditions": "is_sector_lending_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_business_type_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "select_business_type",
                "conditions": "is_business_type_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_requirements_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "requirements",
                "conditions": "is_requirements_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_select_udyam_advisor_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "select_udyam_advisor",
                "conditions": "is_select_udyam_advisor_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_confirm_udyam_advisor_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "confirm_udyam_advisor",
                "conditions": "is_confirm_udyam_advisor_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_udyam_form_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "udyam_registration_form",
                "conditions": "is_udyam_form_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_select_advisor_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "select_advisor",
                "conditions": "is_select_advisor_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_confirm_advisor_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "confirm_advisor",
                "conditions": "is_confirm_advisor_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_documents_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "submit_documents",
                "conditions": "is_documents_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "process_slot_options",
                "dest": "process_query",
                "conditions": "is_random_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "generate_query_response",
                "dest": "select_lawyer_slot",
                "conditions": "is_slot_query",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "select_options_main",
                "dest": "odr_know_more",
                "conditions": "is_odr",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "odr_know_more",
                "dest": "odr_info",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "odr_know_more",
                "dest": "explore_odr",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "explore_odr",
                "dest": "fetch_odr_providers",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "explore_odr",
                "dest": "ask_further_assistance",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "fix_provider",
                "dest": "collect_details",
                "conditions": "is_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "form_filled",
                "dest": "collect_details",
                "conditions": "is_invalid_email",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "fix_provider",
                "dest": "fetch_odr_providers",
                "conditions": "is_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "fix_selected_provider",
                "dest": "send_link_odr",
                "conditions": "is_confirmed",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "fix_selected_provider",
                "dest": "fetch_odr_providers",
                "conditions": "is_not_confirmed",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "fetch_odr_providers",
                "dest": "ask_further_assistance",
                "conditions": "if_search_req_failed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "selected_provider_details",
                "dest": "ask_further_assistance",
                "conditions": "if_select_req_failed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "fix_selected_provider",
                "dest": "ask_further_assistance",
                "conditions": "if_init_req_failed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "send_link_odr",
                "dest": "ask_further_assistance",
            }
        )
        transitions.reverse()
        Machine(model=self, states=FSM.states, transitions=transitions, initial="zero")

    # helper functions
    def yes_or_no(self, message):
        services = [
            OptionsListType(id="1", title="Yes"),
            OptionsListType(id="2", title="No"),
        ]
        self.cb(
            FSMOutput(
                text=message,
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )

    def create_options(self, message, services_data, menu_selector=None):
        services = [
            OptionsListType(id=str(i), title=title)
            for i, title in enumerate(services_data, start=1)
        ]
        self.cb(
            FSMOutput(
                text=message,
                type=MessageType.INTERACTIVE,
                options_list=services,
                menu_selector=menu_selector,
            )
        )

    def is_valid_email(self, email):
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z-.]+$"
        regex = re.compile(pattern)
        if regex.match(email):
            return True
        else:
            return False

    def parse_user_input(self, user_input, options):
        for option in options:
            if option in user_input:
                return option
        return None

    def on_enter_process_query(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["query"] = self.input
        self.cb(FSMOutput(text=self.variables["query"], dest="rag_udyam"))
        self.status = Status.WAIT_FOR_CALLBACK

    def on_enter_generate_query_response(self):
        self.status = Status.WAIT_FOR_ME
        chunks = self.input
        chunks = json.loads(chunks)["chunks"]
        knowledge = "\n".join([row["chunk"] for row in chunks])

        if len(chunks) == 0:
            self.cb(
                FSMOutput(
                    text="Sorry, I don't have information about this. Please try again with a different query.\n"
                )
            )
            self.status = Status.MOVE_FORWARD
        else:
            chat_history = self.variables.get("history", [])
            chat_history_str = "\n".join(
                [f"{row['name']}: {row['message']}" for row in chat_history]
            )

            out = llm(
                [
                    sm(
                        f"""You are a legal expert on Indian Laws. Answer the user's query based on the [Knowledge] provided below. Keep the following in mind:

  Answer Based on Provided Texts: Base your answer solely on the information found in [Knowledge].

  Accuracy and Relevance: Ensure that your responses are accurate and relevant to the question asked. Your answers should reflect the content and context of the provided legal texts.

  Admitting Lack of Information: If the information necessary to answer a question is not available in the provided texts, respond with "I don't know." Do not attempt to infer, guess, or provide information outside the scope of the provided texts.

  Citing Sources: When providing an answer, cite the specific text or document from the provided materials. This will help in validating the response and maintaining transparency.

  Confidentiality and Professionalism: Maintain a professional tone in all responses. Ensure confidentiality and do not request or disclose personal information. Be brief and use grade 8 level English.

  Limitations Reminder: Regularly remind the user that your capabilities are limited to the information available in the provided legal texts and that you are an AI model designed to assist with legal information, not provide legal advice.

  Example Interaction:
  User:What are the requirements from my company for it to be officially registered?
  Bot: According to the Companies Act, 2013, the checklist for Private Limited Company Registration includes having at least two directors (with a DIN issued by the Ministry of Corporate Affairs), a unique company name, no minimum capital requirement, and a registered office. Additionally, one director must be a resident of India.

  User: How can I register a business in Germany?
  Bot: Sorry, I don't know.

  User: What is the Capital of Vietnam?
  Bot: Sorry, this doesn't look like a legal question. I can only attempt to answer legal queries related to Udyam.


    [Knowledge]
    {knowledge}

    [Chat History]
    {chat_history_str}
    """
                    ),
                    um(f"User: {self.variables['query']}\nBot: "),
                ]
            )

            # update chat_history
            chat_history.append({"name": "User", "message": self.variables["query"]})
            chat_history.append({"name": "Bot", "message": out})
            self.variables["history"] = chat_history
            self.cb(FSMOutput(text=f"{out}"))

            self.status = Status.MOVE_FORWARD

    # condition checks
    def is_know_more(self):
        return self.input == "1"

    def is_udyam_eligibility(self):
        return self.input == "2"

    def is_consult_advisor(self):
        return self.input == "3"

    def if_gst_registration(self):
        return self.input == "4"

    def is_udyam_registration(self):
        return self.input == "5"

    def is_odr(self):
        return self.input == "6"

    def if_assistance_required(self):
        return self.input == "1"

    def if_assistance_not_required(self):
        return self.input == "2"

    def is_business_eligible(self):
        return self.variables["business_eligible"] == True

    def is_business_not_eligible(self):
        return self.variables["business_eligible"] == False

    def is_confirmed(self):
        return self.input == "1"

    def is_not_confirmed(self):
        return self.input == "2"

    def is_invalid_category(self):
        return self.variables["invalid_category"]

    def is_random_query(self):
        return self.variables["random_query"]

    def is_investment_query(self):
        return self.variables["rag_trigger"] == "investment"

    def is_turnover_query(self):
        return self.variables["rag_trigger"] == "turnover"

    def is_sector_lending_query(self):
        return self.variables["rag_trigger"] == "sector_lending"

    def is_business_type_query(self):
        return self.variables["rag_trigger"] == "business_type"

    def is_requirements_query(self):
        return self.variables["rag_trigger"] == "requirements"

    def is_select_udyam_advisor_query(self):
        return self.variables["rag_trigger"] == "select_udyam_advisor"

    def is_confirm_udyam_advisor_query(self):
        return self.variables["rag_trigger"] == "confirm_udyam_advisor"

    def is_udyam_form_query(self):
        return self.variables["rag_trigger"] == "udyam_form"

    def is_select_advisor_query(self):
        return self.variables["rag_trigger"] == "select_advisor"

    def is_confirm_advisor_query(self):
        return self.variables["rag_trigger"] == "confirm_advisor"

    def is_name_query(self):
        return self.variables["rag_trigger"] == "name"

    def is_business_name_query(self):
        return self.variables["rag_trigger"] == "business_name"

    def is_documents_query(self):
        return self.variables["rag_trigger"] == "documents"

    def is_slot_query(self):
        return self.variables["rag_trigger"] == "slot"

    def if_search_req_failed(self):
        return self.variables["search_req"] == False

    def if_select_req_failed(self):
        return self.variables["select_req"] == False

    def if_init_req_failed(self):
        return self.variables["init_req"] == False

    def is_invalid_email(self):
        return self.variables["invalid_email"]

    # functions of states
    def on_enter_select_language(self):
        self.status = Status.WAIT_FOR_ME
        msg = self.input
        name = self.variables.get("name", "Mukul")
        self.cb(
            FSMOutput(
                text=f"Hi this is VentureBot. I can help you with any legal queries related to setting up a business in India. How can I help you today?",
                type=MessageType.TEXT,
                dialog="language",
                dest="channel",
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def if_dialog_contains_selected_language(self):
        if self.input == "language_selected":
            return True
        return False

    def on_enter_select_options_main(self):
        self.status = Status.WAIT_FOR_ME

        message = (
            "Thank you. I can provide you assistance with the following categories:"
        )
        services_data = [
            "General Enquiry",
            "Udyam Eligibility",
            "Consult Advisor",
            "GST Registration",  # Smaller Text <20 words
            "Udyam Registration",
            "ODR",
        ]
        self.create_options(message, services_data, "Categories")
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_select_options_main(self):
        self.variables["service_picked"] = self.input

    def on_enter_ask_for_question(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Please ask your query regarding general business setup in India"
        self.cb(FSMOutput(text=msg))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_fetch_answer(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["query"] = self.input
        self.cb(FSMOutput(text=self.variables["query"], dest="rag"))
        self.status = Status.WAIT_FOR_CALLBACK

    def on_enter_generate_response(self):
        self.status = Status.WAIT_FOR_ME
        chunks = self.input
        chunks = json.loads(chunks)["chunks"]
        knowledge = "\n".join([row["chunk"] for row in chunks])

        if len(chunks) == 0:
            self.cb(
                FSMOutput(
                    text="Sorry, I don't have information about this. Please try again with a different query.\n"
                )
            )
            self.status = Status.MOVE_FORWARD
        else:
            chat_history = self.variables.get("history", [])
            chat_history_str = "\n".join(
                [f"{row['name']}: {row['message']}" for row in chat_history]
            )

            out = llm(
                [
                    sm(
                        f"""You are a legal expert on Indian Laws. Answer the user's query based on the [Knowledge] provided below. Keep the following in mind:

  Answer Based on Provided Texts: Base your answer solely on the information found in [Knowledge].

  Accuracy and Relevance: Ensure that your responses are accurate and relevant to the question asked. Your answers should reflect the content and context of the provided legal texts.

  Admitting Lack of Information: If the information necessary to answer a question is not available in the provided texts, respond with "I don't know." Do not attempt to infer, guess, or provide information outside the scope of the provided texts.

  Citing Sources: When providing an answer, cite the specific text or document from the provided materials. This will help in validating the response and maintaining transparency.

  Confidentiality and Professionalism: Maintain a professional tone in all responses. Ensure confidentiality and do not request or disclose personal information. Be brief and use grade 8 level English.

  Limitations Reminder: Regularly remind the user that your capabilities are limited to the information available in the provided legal texts and that you are an AI model designed to assist with legal information, not provide legal advice.

  Example Interaction:
  User:What are the requirements from my company for it to be officially registered?
  Bot: According to the Companies Act, 2013, the checklist for Private Limited Company Registration includes having at least two directors (with a DIN issued by the Ministry of Corporate Affairs), a unique company name, no minimum capital requirement, and a registered office. Additionally, one director must be a resident of India.

  User: How can I register a business in Germany?
  Bot: Sorry, I don't know.

  User: What is the Capital of Vietnam?
  Bot: Sorry, this doesn't look like a legal question. I can only attempt to answer legal queries related to business venture, gst, specific to India.


    [Knowledge]
    {knowledge}

    [Chat History]
    {chat_history_str}
    """
                    ),
                    um(f"User: {self.variables['query']}\nBot: "),
                ]
            )

            # update chat_history
            chat_history.append({"name": "User", "message": self.variables["query"]})
            chat_history.append({"name": "Bot", "message": out})
            self.variables["history"] = chat_history
            self.cb(FSMOutput(text=f"{out}"))

            self.status = Status.MOVE_FORWARD

    def on_enter_ask_for_another_question(self):
        self.status = Status.WAIT_FOR_ME
        msg = self.input

        services = [
            OptionsListType(id="1", title="Continue questioning"),
            OptionsListType(id="2", title="Main menu"),
        ]

        self.cb(
            FSMOutput(
                text="Do you have more questions for me regarding setting up a business?",
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )

        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_udyam_check(self):
        self.status = Status.WAIT_FOR_ME
        message = "Thank you for your input. Would you like to know about Udyam before proceeding for an eligibity check?"
        self.yes_or_no(message=message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_give_udyam_info(self):
        self.status = Status.WAIT_FOR_ME
        file_path = os.path.join(os.getcwd(), "pulse", "data", "udyam.pdf")

        # Check if the file exists
        if os.path.exists(file_path):
            upload_file = UploadFile(
                filename="udyam.pdf",
                path=file_path,
                mime_type="application/pdf",
            )
            self.cb(
                FSMOutput(
                    text="Udyam Information",
                    file=upload_file,
                    dest="channel",
                    type=MessageType.DOCUMENT,
                )
            )
            self.status = Status.MOVE_FORWARD
        else:
            print("File not found:", file_path)
        self.status = Status.MOVE_FORWARD

    def on_enter_ask_for_udyam_question(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Please ask your query regarding Udyam"
        self.cb(FSMOutput(text=msg))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_for_udyam_question(self):
        self.variables["udyam_query"] = self.input

    def on_enter_fetch_udyam_answer(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text=self.variables["udyam_query"], dest="rag_udyam"))
        self.status = Status.WAIT_FOR_CALLBACK

    def on_enter_generate_udyam_response(self):
        self.status = Status.WAIT_FOR_ME
        chunks = self.input
        chunks = json.loads(chunks)["chunks"]
        knowledge = "\n".join([row["chunk"] for row in chunks])

        if len(chunks) == 0:
            self.cb(
                FSMOutput(
                    text="Sorry, I don't have information about this. Please try again with a different query.\n"
                )
            )
            self.status = Status.MOVE_FORWARD
        else:
            chat_history = self.variables.get("history", [])
            chat_history_str = "\n".join(
                [f"{row['name']}: {row['message']}" for row in chat_history]
            )

            out = llm(
                [
                    sm(
                        f"""You are a legal expert on Indian Laws. Answer the user's query based on the [Knowledge] provided below. Keep the following in mind:

  Answer Based on Provided Texts: Base your answer solely on the information found in [Knowledge].

  Accuracy and Relevance: Ensure that your responses are accurate and relevant to the question asked. Your answers should reflect the content and context of the provided legal texts.

  Admitting Lack of Information: If the information necessary to answer a question is not available in the provided texts, respond with "I don't know." Do not attempt to infer, guess, or provide information outside the scope of the provided texts.

  Citing Sources: When providing an answer, cite the specific text or document from the provided materials. This will help in validating the response and maintaining transparency.

  Confidentiality and Professionalism: Maintain a professional tone in all responses. Ensure confidentiality and do not request or disclose personal information. Be brief and use grade 8 level English.

  Limitations Reminder: Regularly remind the user that your capabilities are limited to the information available in the provided legal texts and that you are an AI model designed to assist with legal information, not provide legal advice.

  Example Interaction:
  User:What are the requirements from my company for it to be officially registered?
  Bot: According to the Companies Act, 2013, the checklist for Private Limited Company Registration includes having at least two directors (with a DIN issued by the Ministry of Corporate Affairs), a unique company name, no minimum capital requirement, and a registered office. Additionally, one director must be a resident of India.

  User: How can I register a business in Germany?
  Bot: Sorry, I don't know.

  User: What is the Capital of Vietnam?
  Bot: Sorry, this doesn't look like a legal question. I can only attempt to answer legal queries related to Udyam.


    [Knowledge]
    {knowledge}

    [Chat History]
    {chat_history_str}
    """
                    ),
                    um(f"User: {self.variables['udyam_query']}\nBot: "),
                ]
            )

            # update chat_history
            chat_history.append(
                {"name": "User", "message": self.variables["udyam_query"]}
            )
            chat_history.append({"name": "Bot", "message": out})
            self.variables["history"] = chat_history
            self.cb(FSMOutput(text=f"{out}"))

            self.status = Status.MOVE_FORWARD

    def on_enter_ask_for_another_udyam_question(self):
        self.status = Status.WAIT_FOR_ME
        msg = self.input

        services = [
            OptionsListType(id="1", title="Continue questioning"),
            OptionsListType(id="2", title="Skip"),
        ]

        self.cb(
            FSMOutput(
                text="Do you have more questions for me regarding Udyam?",
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )

        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_ask_details(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Now, please answer a few questions to help us identify your business category under Udyam."
        self.cb(FSMOutput(text=msg))
        self.status = Status.MOVE_FORWARD

    def on_enter_ask_investment(self):
        self.status = Status.WAIT_FOR_ME
        message = "What is your expected/current investment?"
        services_data = ["less than 1 Crore", "1 Cr < 10 Cr", "10 Cr < 20 Cr"]
        self.create_options(message, services_data)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_investment(self):
        self.variables["investment"] = self.input

    def on_enter_process_investment_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "investment"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2", "3"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_ask_turnover(self):
        self.status = Status.WAIT_FOR_ME
        services_data = ["less than 5 Crore", "5 Cr < 50 Cr", "50 Cr < 250 Cr"]
        msg = "What is your expected/current annual turnover?"
        self.create_options(msg, services_data)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_turnover(self):
        self.variables["turnover"] = self.input

    def on_enter_process_turnover_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "turnover"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2", "3"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_evaluate_category(self):
        self.status = Status.WAIT_FOR_ME
        message = ""
        if self.variables["investment"] == self.variables["turnover"]:
            message = "Thankyou for sharing those details,"
            if self.variables["investment"] == "1":
                message += "You are a micro business as per Udyam"
            elif self.variables["investment"] == "2":
                message += "You are a small business as per Udyam"
            else:
                message += "You are a medium business as per Udyam"
            self.cb(
                FSMOutput(
                    text=message,
                )
            )
            self.variables["invalid_category"] = False
        else:
            message = "That input does not qualify your business as an MSME as per Udyam. Please try again."
            self.cb(FSMOutput(text=message))
            self.variables["invalid_category"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_ask_for_sector_lending(self):
        self.status = Status.WAIT_FOR_ME
        message = "Would you like to know if your business is eligible for Priority Sector Lending under Udyam?"
        self.yes_or_no(message=message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_process_sector_lending_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "sector_lending"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_select_business_type(self):
        self.status = Status.WAIT_FOR_ME
        message = "Is your business type one of the following?\n1. Agriculture\n2. Manufacturing\n3. Education\n4. Healthcare\n5. Renewable energy"
        self.yes_or_no(message=message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_process_business_type_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "business_type"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_process_business_type_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_sector_lending_eligible(self):
        self.status = Status.WAIT_FOR_ME
        message = "Congrats you are eligible for Priority Sector Lending."
        self.cb(FSMOutput(text=message))
        self.status = Status.MOVE_FORWARD

    def on_enter_sector_lending_not_eligible(self):
        self.status = Status.WAIT_FOR_ME
        message = "I'm sorry, you are not eligible for Priority Sector Lending."
        self.cb(FSMOutput(text=message))
        self.status = Status.MOVE_FORWARD

    def on_enter_requirements(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["udyam_flow"] = True
        self.cb(
            FSMOutput(
                text="Let us find out if you are eligible for Udyam registration currently",
                whatsapp_flow_id="383257324629158",
                whatsapp_screen_id="DOCUMENTS_CHECK_FORM",
                dest="channel",
                type=MessageType.FORM,
                form_token=str(uuid.uuid4()),
                menu_selector="Documents check for Udyam",
                footer="Enter details",
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_requirements(self):
        self.status = Status.WAIT_FOR_ME
        form_input = json.loads(self.input)
        self.variables["documents"] = form_input
        self.variables["has_aadhar"] = self.variables["documents"]["aadhaar"]
        self.variables["has_pan"] = self.variables["documents"]["pan"]
        self.variables["has_gst_number"] = self.variables["documents"]["gst"]
        self.variables["has_prev"] = self.variables["documents"]["registered_em_uam"]
        self.status = Status.MOVE_FORWARD

    def on_enter_process_requirements_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "requirements"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_ask_aadhar(self):
        self.status = Status.WAIT_FOR_ME
        message = "Do you have an Aadhaar number?"
        self.yes_or_no(message=message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_aadhar(self):
        self.variables["has_aadhar"] = self.input

    def on_enter_ask_pan(self):
        self.status = Status.WAIT_FOR_ME
        message = "Do you have a PAN?"
        self.yes_or_no(message=message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_pan(self):
        self.variables["has_pan"] = self.input

    def on_enter_ask_gst_number(self):
        self.status = Status.WAIT_FOR_ME
        message = "Do you have a GST number?"
        self.yes_or_no(message=message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_gst_number(self):
        self.variables["has_gst_number"] = self.input

    def on_enter_ask_prev(self):
        self.status = Status.WAIT_FOR_ME
        message = "Have you previously registered under EM-II or UAM?"
        self.yes_or_no(message=message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_prev(self):
        self.variables["has_prev"] = self.input

    def on_enter_evaluate_eligibility(self):
        self.status = Status.WAIT_FOR_ME
        has_aadhar = self.variables.get("has_aadhar")
        has_pan = self.variables.get("has_pan")
        has_gst_number = self.variables.get("has_gst_number")
        has_prev = self.variables.get("has_prev")

        if (
            has_aadhar == "0"
            and has_pan == "0"
            and has_gst_number == "0"
            and has_prev == "0"
        ):
            self.variables["business_eligible"] = True
            self.status = Status.MOVE_FORWARD

        else:
            self.variables["business_eligible"] = False
            msg = "Please get "
            if has_aadhar != "0":
                msg += "Aadhaar, "

            if has_pan != "0":
                msg += "PAN, "

            if has_prev != "0":
                msg += "previously registered under EM-II or UAM, "

            if has_gst_number != "0":
                msg += "GSTIN"

            msg += "to initiate Udyam Registration"
            self.cb(FSMOutput(text=msg))
            self.status = Status.MOVE_FORWARD

    def on_enter_ask_for_gst_assistance(self):
        self.status = Status.WAIT_FOR_ME
        if self.variables["has_gst_number"] != "1":
            msg = "Would you like help with GST Registration?"
            self.yes_or_no(msg)
            self.status = Status.WAIT_FOR_USER_INPUT
        else:
            self.status = Status.MOVE_FORWARD

    def on_enter_ask_for_udyam_assistance(self):
        self.status = Status.WAIT_FOR_ME
        message = "Business is eligible for Udyam Registration.\nDo you need help in filing Udyam Registration?"
        self.cb(FSMOutput(text=message))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_fetch_udyam_advisors(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Thanks for your selection. Here's a list of service providers that can assist you with the registration. You can click on each to see more information, their availability, and a rough quote. Please select one."
        self.cb(FSMOutput(text=msg))

        try:
            columns = {
                "SN": "service_number",
                "Provider name": "provider_name",
                "Provider Short Desc": "short_desc",
                "Provider Long Desc": "long_desc",
                "Provider Addnt Desc URL": "url",
                "Provider Image": "image",
                "item.descriptor.code": "descriptor_code",
                "item.descriptor.name": "descriptor_name",
                "item.descriptor.short_desc": "descriptor_short_desc",
                "item.descriptor.long_desc": "descriptor_long_desc",
                "item.descriptor.Images": "descriptor_images",
                "item base fee": "base_fee",
                "Item per hearing fee": "item_per_hearing_fee",
                "categories_id": "categories_id",
                "intent.fulfillment.time": "intent_fulfillment_time",
            }
            df = pd.read_excel(
                "pulse/data/venture_dummy_catalog.xlsx", usecols=columns.keys()
            )
            df = df.rename(columns=columns)
            providers = []

            for i, row in df.iterrows():
                provider_name = row["provider_name"]
                short_desc = row["short_desc"]
                long_desc = row["long_desc"]
                url = row["url"]
                # image = row['image']
                descriptor_code = row["descriptor_code"]
                descriptor_name = row["descriptor_name"]
                descriptor_short_desc = row["descriptor_short_desc"]
                descriptor_long_desc = row["descriptor_long_desc"]
                descriptor_images = row["descriptor_images"]
                base_fee = row["base_fee"]
                item_per_hearing_fee = row["item_per_hearing_fee"]

                timestamp_obj = datetime.fromisoformat(
                    row["intent_fulfillment_time"].replace("Z", "+00:00")
                )

                # Convert datetime object to Unix timestamp
                readable_timestamp = timestamp_obj.strftime("%Y-%m-%d %H:%M")

                self.cb(
                    FSMOutput(
                        text=f"{provider_name}\n{short_desc}\n{long_desc}\nURL: {url}\nBase Fee: {base_fee}\nItem per Hearing Fee: {item_per_hearing_fee}\nFulfillment Time: {readable_timestamp}",
                        type=MessageType.INTERACTIVE,
                        # media_url=image,
                        options_list=[
                            OptionsListType(id=str(i + 1), title="Book Appointment")
                        ],
                        footer="Click below to book this advocate",
                        header=provider_name,
                    )
                )
                providers.append(
                    {
                        "id": row["service_number"],
                        "provider_name": row["provider_name"],
                        "base_fee": row["base_fee"],
                        "intent_fulfillment_time": readable_timestamp,
                    }
                )

        except FileNotFoundError:
            print("Error: business_venture.xlsx not found.")

        self.variables["providers"] = providers
        self.status = Status.MOVE_FORWARD

    def on_enter_select_udyam_advisor(self):
        self.status = Status.WAIT_FOR_ME
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_select_udyam_advisor(self):
        selected_provider = self.variables["providers"][self.input - 1]
        self.variables["selected_provider"] = selected_provider["id"]
        self.variables["selected_provider_name"] = selected_provider["provider_name"]
        self.variables["selected_base_fee"] = selected_provider["base_fee"]
        self.variables["intent_fulfillment_time"] = selected_provider[
            "intent_fulfillment_time"
        ]

        self.cb(
            FSMOutput(
                header=f"Selected Provider: {self.variables['selected_provider_name']}",
                text=f"Base Fee: {self.variables['selected_base_fee']}\n Available Slots: {self.variables['intent_fulfillment_time']}\n",
            )
        )

    def on_enter_process_select_udyam_advisor_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "select_udyam_advisor"
        self.variables["random_query"] = False
        if (
            self.parse_user_input(
                self.input, range(1, len(self.variables["providers"]) + 1)
            )
            is None
        ):
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def is_not_valid_udyam_advisor(self):
        if self.input is None:
            return True
        try:
            self.input = int(self.input)
            if self.input < 1 or self.input > len(self.variables["providers"]):
                return True
        except Exception:
            return True
        return False

    def on_enter_ask_to_select_udyam_advisor_again(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Sorry, Your selected legal service provider is not valid.Please select a valid provider."
        self.cb(FSMOutput(text=msg))
        self.status = Status.MOVE_FORWARD

    def on_enter_confirm_udyam_advisor(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Thanks. Are you sure you want to move forward with your selection? Please reply with 'Yes' or 'No'."
        self.yes_or_no(msg)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_process_confirm_udyam_advisor_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "confirm_udyam_advisor"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_udyam_registration_form(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(
            FSMOutput(
                text="Please fill in the Udyam Registration Form details below.",
                whatsapp_flow_id="1378398356174070",
                whatsapp_screen_id="UDYAM_REGISTRATION_FORM",
                dest="channel",
                type=MessageType.FORM,
                form_token=str(uuid.uuid4()),
                menu_selector="Register for Udyam",
                menu_title="Register for Udyam",
                footer="Enter details",
                header="Udyam Registration",
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_udyam_registration_form(self):
        self.status = Status.WAIT_FOR_ME
        form_input = json.loads(self.input)
        self.variables["form_input"] = form_input
        self.status = Status.MOVE_FORWARD

    def on_enter_process_udyam_form_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "udyam_form"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_gst_registration(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["gst_flow"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_fetch_advisors(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Thanks for your selection. Here's a list of service providers that can assist you with the registration. You can click on each to see more information, their availability, and a rough quote. Please select one."
        self.cb(FSMOutput(text=msg))

        try:
            columns = {
                "SN": "service_number",
                "Provider name": "provider_name",
                "Provider Short Desc": "short_desc",
                "Provider Long Desc": "long_desc",
                "Provider Addnt Desc URL": "url",
                "Provider Image": "image",
                "item.descriptor.code": "descriptor_code",
                "item.descriptor.name": "descriptor_name",
                "item.descriptor.short_desc": "descriptor_short_desc",
                "item.descriptor.long_desc": "descriptor_long_desc",
                "item.descriptor.Images": "descriptor_images",
                "item base fee": "base_fee",
                "Item per hearing fee": "item_per_hearing_fee",
                "categories_id": "categories_id",
                "intent.fulfillment.time": "intent_fulfillment_time",
            }
            df = pd.read_excel(
                "pulse/data/venture_dummy_catalog.xlsx", usecols=columns.keys()
            )
            df = df.rename(columns=columns)
            providers = []

            for i, row in df.iterrows():
                provider_name = row["provider_name"]
                short_desc = row["short_desc"]
                long_desc = row["long_desc"]
                url = row["url"]
                # image = row['image']
                descriptor_code = row["descriptor_code"]
                descriptor_name = row["descriptor_name"]
                descriptor_short_desc = row["descriptor_short_desc"]
                descriptor_long_desc = row["descriptor_long_desc"]
                descriptor_images = row["descriptor_images"]
                base_fee = row["base_fee"]
                item_per_hearing_fee = row["item_per_hearing_fee"]

                timestamp_obj = datetime.fromisoformat(
                    row["intent_fulfillment_time"].replace("Z", "+00:00")
                )

                # Convert datetime object to Unix timestamp
                readable_timestamp = timestamp_obj.strftime("%Y-%m-%d %H:%M")

                self.cb(
                    FSMOutput(
                        text=f"{provider_name}\n{short_desc}\n{long_desc}\nURL: {url}\nBase Fee: {base_fee}\nItem per Hearing Fee: {item_per_hearing_fee}\nFulfillment Time: {readable_timestamp}",
                        type=MessageType.INTERACTIVE,
                        # media_url=image,
                        options_list=[
                            OptionsListType(id=str(i + 1), title="Book Appointment")
                        ],
                        footer="Click below to book this advocate",
                        header=provider_name,
                    )
                )
                providers.append(
                    {
                        "id": row["service_number"],
                        "provider_name": row["provider_name"],
                        "base_fee": row["base_fee"],
                        "intent_fulfillment_time": readable_timestamp,
                    }
                )

        except FileNotFoundError:
            print("Error: business_venture.xlsx not found.")

        self.variables["providers"] = providers
        self.status = Status.MOVE_FORWARD

    def on_enter_select_advisor(self):
        self.status = Status.WAIT_FOR_ME
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_select_advisor(self):
        selected_provider = self.variables["providers"][self.input - 1]
        self.variables["selected_provider"] = selected_provider["id"]
        self.variables["selected_provider_name"] = selected_provider["provider_name"]
        self.variables["selected_base_fee"] = selected_provider["base_fee"]
        self.variables["intent_fulfillment_time"] = selected_provider[
            "intent_fulfillment_time"
        ]

        self.cb(
            FSMOutput(
                header=f"Selected Provider: {self.variables['selected_provider_name']}",
                text=f"Base Fee: {self.variables['selected_base_fee']}\n Available Slots: {self.variables['intent_fulfillment_time']}\n",
            )
        )

    def on_enter_process_select_advisor_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "select_advisor"
        self.variables["random_query"] = False
        if (
            self.parse_user_input(
                self.input, range(1, len(self.variables["providers"]) + 1)
            )
            is None
        ):
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def is_not_valid_advisor(self):
        if self.input is None:
            return True
        try:
            self.input = int(self.input)
            if self.input < 1 or self.input > len(self.variables["providers"]):
                return True
        except Exception:
            return True
        return False

    def on_enter_ask_to_select_advisor_again(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Sorry, Your selected legal service provider is not valid.Please select a valid provider."
        self.cb(FSMOutput(text=msg))
        self.status = Status.MOVE_FORWARD

    def on_enter_confirm_advisor(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Thanks. Are you sure you want to move forward with your selection? Please reply with 'Yes' or 'No'."
        self.yes_or_no(msg)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_process_confirm_advisor_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "confirm_advisor"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_ask_name(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(
            FSMOutput(
                text="Please enter your name",
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_name(self):
        self.variables["name"] = self.input

    def on_enter_ask_business_name(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(
            FSMOutput(
                text="Please enter your business name",
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_business_name(self):
        self.variables["business_name"] = self.input

    def on_enter_select_business_category(self):
        self.status = Status.WAIT_FOR_ME
        message = "Please choose your business category from the following"
        services_data = [
            "Individual & Sole Properietor",
            "Partnership & LLP",
            "Company",
        ]
        self.create_options(message, services_data)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_select_business_category(self):
        self.variables["business_category"] = self.input

    def on_enter_ask_documents(self):
        self.status = Status.WAIT_FOR_ME
        message = "Thanks for confirming. You will need to submit the following documents with us.\n"
        if self.variables["business_category"] == "1":
            message += "1. Owneer's PAN card\n2. Owner's Aadhaar card\n3. Owner's photograph\n4. Proof of Address\n5. Bank account details\n"
        elif self.variables["business_category"] == "2":
            message += "1. Partnership deed\n2. PAN cards of partners involved\n3. Photographs of the partners involved\n4. Address proof of partners involved\n5. Aadhaar card of any authorised signatory\n6. Signatory proof of appointment\n7. LLP proof of registration\n8. Bank details\n9. Business principal address proof\n"
        elif self.variables["business_category"] == "3":
            message += "1. Company PAN card\n2. The Ministry of Corporate Affairs incorporation certificate Memorandum/ articles of association Signatory appointment proof\n3. Signatory PAN card\n4. Signatory Aadhaar card\n5. PAN card of all directors Address proof of all directors\n6. Bank details\n7. Business principal address\n"
        self.cb(FSMOutput(text=message))
        self.status = Status.MOVE_FORWARD

    def on_enter_submit_documents(self):
        self.status = Status.WAIT_FOR_ME
        services = [
            OptionsListType(id="1", title="Upload Documents"),
        ]
        self.cb(
            FSMOutput(
                text="Click on upload documents and submit.",
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_process_documents_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "documents"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_select_lawyer_slot(self):
        self.status = Status.WAIT_FOR_ME
        message = "Thanks. We will now connect you with our lawyers. Please choose one of the available time and date slots."
        services_data = ["25-04-2024 10:00 AM", "26-04-2024 11:00 AM"]
        self.create_options(message, services_data)
        self.variables["udyam_flow"] = False
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_process_slot_options(self):
        self.status = Status.WAIT_FOR_ME
        self.variables["rag_trigger"] = "slot"
        self.variables["random_query"] = False
        if self.parse_user_input(self.input, ["1", "2"]) is None:
            self.variables["random_query"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_send_link(self):
        self.status = Status.WAIT_FOR_ME
        link = "https://dummylinkforthecall/"
        message = (
            f"Thanks for confirming. Here is the link for the call: {format(link)}"
        )
        output = FSMOutput(text=message)
        self.cb(output)
        self.status = Status.MOVE_FORWARD

    def on_enter_odr_know_more(self):
        self.status = Status.WAIT_FOR_ME
        message = "Would you like to know more about online dispute resolutiom (ODR) before proceeding?"
        self.yes_or_no(message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_odr_info(self):
        self.status = Status.WAIT_FOR_ME
        message = "Online Dispute Resolution (ODR) refers to the use of digital platforms and technologies to resolve disputes outside of courts. It encompasses various processes such as mediation & arbitration, facilitated online. ODR is designed to offer a more accessible, cost-effective, and speedy resolution to disputes compared to traditional litigation. For cheque bouncing disputes, ODR platforms can facilitate negotiations between parties or offer mediation services to resolve such disputes efficiently, without the need for lengthy court procedures. This can save time and resources for both parties and reduce the backlog of cases in the judiciary."
        self.cb(FSMOutput(text=message))
        self.status = Status.MOVE_FORWARD

    def on_enter_explore_odr(self):
        self.status = Status.WAIT_FOR_ME
        message = "Would you like to explore ODR to resolve your dispute? Please note that availing the services of ODR platforms will have a fee being levied based on the service provider, nature of your dispute and number of hearings that will take place."
        self.yes_or_no(message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_fetch_odr_providers(self):
        self.status = Status.WAIT_FOR_ME
        url = "https://ps-bap-client.becknprotocol.io/search"
        data = {
            "context": {
                "domain": "online-dispute-resolution:0.1.0",
                "location": {"country": {"code": "IND"}},
                "transaction_id": "",
                "message_id": "",
                "action": "search",
                "timestamp": "",
                "version": "1.1.0",
                "bap_id": "ps-bap-network.becknprotocol.io",
                "bap_uri": "https://ps-bap-network.becknprotocol.io",
                "ttl": "PT10M",
            },
            "message": {
                "intent": {
                    "item": {"descriptor": {"name": "financial disputes"}},
                }
            },
        }
        response = requests.post(url, json=data)
        if response.status_code == 200:
            self.parse_search_response(response.json())
        else:
            logger.error(
                f"Request to {url} failed. Status code: {response.status_code}\n Error msg: {response.text}"
            )
            self.cb(
                FSMOutput(
                    text="Sorry for the inconvinience, please try again after some time"
                )
            )
            self.variables["search_req"] = False

        self.status = Status.MOVE_FORWARD

    def parse_search_response(self, response_data):
        if response_data["responses"] == []:
            self.cb(
                FSMOutput(
                    text="Pulse server seems to be down, please try again in sometime"
                )
            )
            self.variables["search_req"] = False
        else:
            providers = []
            i = 0
            for resp in response_data["responses"]:
                if "providers" in resp["message"]:
                    for provider in resp["message"]["providers"]:
                        provider_info = {
                            "bpp_id": resp["context"]["bpp_id"],
                            "bpp_uri": resp["context"]["bpp_uri"],
                            "id": provider["id"],
                            "name": provider["descriptor"]["name"],
                            "short_desc": provider["descriptor"]["short_desc"],
                            "long_desc": provider["descriptor"]["long_desc"],
                            "url": provider["descriptor"]["additional_desc"]["url"],
                        }
                        providers.append(provider_info)
                        self.cb(
                            FSMOutput(
                                text=f"{provider_info['short_desc']}\n{provider_info['long_desc']}\nURL: {provider_info['url']}",
                                type=MessageType.INTERACTIVE,
                                # media_url=image,
                                options_list=[
                                    OptionsListType(id=str(i + 1), title="Know more")
                                ],
                                header=provider_info.get("name"),
                            )
                        )
                        i += 1
                else:
                    print("No providers found in the response")

            self.variables["search_req"] = True
            self.variables["odr_providers"] = providers

    def on_enter_select_odr_provider(self):
        self.status = Status.WAIT_FOR_ME
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_select_odr_provider(self):
        self.variables["selected_provider"] = self.variables["odr_providers"][
            int(self.input) - 1
        ]

    def on_enter_selected_provider_details(self):
        self.status = Status.WAIT_FOR_ME
        url = "https://ps-bap-client.becknprotocol.io/select"
        data = {
            "context": {
                "domain": "online-dispute-resolution:0.1.0",
                "location": {"country": {"code": "IND"}},
                "transaction_id": "",
                "message_id": "",
                "action": "select",
                "timestamp": "",
                "version": "1.1.0",
                "bap_uri": "https://ps-bap-network.becknprotocol.io",
                "bap_id": "ps-bap-network.becknprotocol.io",
                "bpp_id": self.variables["selected_provider"]["bpp_id"],
                "bpp_uri": self.variables["selected_provider"]["bpp_uri"],
                "ttl": "PT10M",
            },
            "message": {
                "order": {
                    "providers": {"id": self.variables["selected_provider"]["id"]}
                }
            },
        }
        response = requests.post(url, json=data)
        if response.status_code == 200:
            self.parse_select_response(response.json())
        else:
            logger.error(
                f"Request to {url} failed. Status code: {response.status_code}\n Error msg: {response.text}"
            )
            self.cb(
                FSMOutput(
                    text="Sorry for the inconvinience, please try again in some time"
                )
            )
            self.variables["select_req"] = False
        self.status = Status.MOVE_FORWARD

    def parse_select_response(self, response_data):
        self.status = Status.WAIT_FOR_ME
        if response_data["responses"] == []:
            self.cb(
                FSMOutput(
                    text="Pulse server seems to be down, please try again in sometime"
                )
            )
            logger.error(f"No responses found from bpp providers")
            self.variables["select_req"] = False
        else:
            resp = response_data["responses"][0]
            self.variables["selected_provider"].update(
                {
                    "quote": resp["message"]["order"]["quote"]["price"]["value"],
                    "base_fee": resp["message"]["order"]["quote"]["breakup"][0][
                        "price"
                    ]["value"],
                    "fee_per_hearing": resp["message"]["order"]["quote"]["breakup"][1][
                        "price"
                    ]["value"],
                }
            )
            info = self.variables["selected_provider"]
            message = f"{info['short_desc']}\n"
            message += f"{info['long_desc']}\n"
            message += f"{info['url']}\n"
            message += f"Base Fee: Rs. {info['base_fee']}\n"
            message += f"Fee per Hearing: Rs. {info['fee_per_hearing']}\n"
            message += f"Total Fee: Rs. {info['quote']}"
            self.cb(FSMOutput(text=message, header=info["name"]))
            self.variables["select_req"] = True

    def on_enter_fix_provider(self):
        self.status = Status.WAIT_FOR_ME
        message = "Would you like to go ahead with this provider?"
        self.yes_or_no(message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_collect_details(self):
        self.status = Status.WAIT_FOR_ME
        if (
            "invalid_email" in self.variables
            and self.variables["invalid_email"] == True
        ):
            self.cb(
                FSMOutput(
                    text="Please enter a valid complainant email address",
                    whatsapp_flow_id="304363379377221",
                    whatsapp_screen_id="VENTURE_DISPUTE_FORM",
                    dest="channel",
                    type=MessageType.FORM,
                    form_token=str(uuid.uuid4()),
                    menu_selector="Register Dispute",
                    menu_title="Register Dispute",
                    footer="Enter details",
                    header="Complaint Registration",
                )
            )
        else:
            self.cb(
                FSMOutput(
                    text="Please fill in the details below.",
                    whatsapp_flow_id="304363379377221",
                    whatsapp_screen_id="VENTURE_DISPUTE_FORM",
                    dest="channel",
                    type=MessageType.FORM,
                    form_token=str(uuid.uuid4()),
                    menu_selector="Register Dispute",
                    menu_title="Register Dispute",
                    footer="Enter details",
                    header="Complaint Registration",
                )
            )

        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_form_filled(self):
        self.status = Status.WAIT_FOR_ME
        form_data_dict = json.loads(self.input)
        if self.is_valid_email(form_data_dict["c_email"]):
            self.variables["invalid_email"] = False
            self.variables["r_name"] = form_data_dict["r_name"]
            self.variables["r_phone"] = form_data_dict["r_phone"]
            self.variables["r_email"] = form_data_dict["r_email"]
            self.variables["c_name"] = form_data_dict["c_name"]
            self.variables["c_phone"] = form_data_dict["c_phone"]
            self.variables["c_email"] = form_data_dict["c_email"]
            self.variables["c_address"] = form_data_dict["c_address"]
            self.variables["c_city"] = form_data_dict["c_city"]
            self.variables["dispute_details"] = form_data_dict["dispute_details"]
            if "claim_value" in form_data_dict:
                self.variables["claim_value"] = form_data_dict["claim_value"]
        else:
            self.variables["invalid_email"] = True
        self.status = Status.MOVE_FORWARD

    def on_enter_consent_form(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(
            FSMOutput(
                text="Please fill in the ODR consent form below.",
                whatsapp_flow_id="1564471277665750",
                whatsapp_screen_id="VENTURE_CONSENT_FORM",
                dest="channel",
                type=MessageType.FORM,
                form_token=str(uuid.uuid4()),
                menu_selector="Consent Form",
                menu_title="Consent Form",
                header="Consent Form",
            )
        )
        self.status = Status.MOVE_FORWARD
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_confirm_odr_provider(self):
        self.status = Status.WAIT_FOR_ME
        url = "https://ps-bap-client.becknprotocol.io/init"
        data = self.init_request_body(
            "respondent",
            self.variables["r_name"],
            self.variables["r_phone"],
            self.variables["r_email"],
            "c844d5f4-29c3-4398-b594-8b4716ef5dbf",
        )
        response = requests.post(url, json=data)
        if response.status_code == 200:
            logger.info(f"init consent form response: {response.json()}")
            self.variables["init_req"] = True

        else:
            logger.error(
                f"Request to {url} failed. Status code: {response.status_code}\n Error msg: {response.text}"
            )
            self.variables["init_req"] = False

        data = self.init_request_body(
            "dispute-details",
            self.variables["c_name"],
            self.variables["c_email"],
            self.variables["c_phone"],
            "c844d5f4-29c3-4398-b594-8b4716ef5dbf",
        )
        response = requests.post(url, json=data)
        if response.status_code == 200:
            logger.info(f"init consent form response: {response.json()}")
            self.variables["init_req"] = True

        else:
            logger.error(
                f"Request to {url} failed. Status code: {response.status_code}\n Error msg: {response.text}"
            )
            self.variables["init_req"] = False

        data = self.init_request_body(
            "consent-form",
            self.variables["c_name"],
            self.variables["c_email"],
            self.variables["c_phone"],
            "c844d5f4-29c3-4398-b594-8b4716ef5dbf",
        )
        response = requests.post(url, json=data)
        if response.status_code == 200:
            logger.info(f"init consent form response: {response.json()}")
            self.variables["init_req"] = True

        else:
            logger.error(
                f"Request to {url} failed. Status code: {response.status_code}\n Error msg: {response.text}"
            )
            self.variables["init_req"] = False

        self.status = Status.MOVE_FORWARD

    def init_request_body(
        self,
        tag_name,
        fulfillment_name,
        fulfillment_email,
        fulfillment_phone,
        submission_id,
    ):
        return {
            "context": {
                "domain": "online-dispute-resolution:0.1.0",
                "location": {"country": {"code": "IND"}},
                "action": "init",
                "version": "1.1.0",
                "transaction_id": "",
                "message_id": "",
                "timestamp": "",
                "bap_uri": "https://ps-bap-network.becknprotocol.io",
                "bap_id": "ps-bap-network.becknprotocol.io",
                "bpp_id": self.variables["selected_provider"]["bpp_id"],
                "bpp_uri": self.variables["selected_provider"]["bpp_uri"],
                "ttl": "PT10M",
            },
            "message": {
                "order": {
                    "provider": {"id": self.variables["selected_provider"]["id"]},
                    "items": [
                        {
                            "id": "ALPHA-ARB-01",
                            "xinput": {"form": {"submission_id": submission_id}},
                        }
                    ],
                    "billing": {
                        "name": self.variables["c_name"],
                        "email": self.variables["c_email"],
                        "address": self.variables["c_address"],
                        "city": {"name": self.variables["c_city"]},
                    },
                    "fulfillments": [
                        {
                            "customer": {
                                "person": {"name": fulfillment_name},
                                "contact": {
                                    "phone": fulfillment_phone,
                                    "email": fulfillment_email,
                                },
                            }
                        }
                    ],
                    "tags": [{"descriptor": {"name": tag_name}}],
                }
            },
        }

    def on_enter_fix_selected_provider(self):
        self.status = Status.WAIT_FOR_ME
        message = f"Rs. {self.variables['selected_provider']['quote']} is your fee, would you like to confirm your selection and initiate the ODR process?"
        self.yes_or_no(message)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_send_link_odr(self):
        self.status = Status.WAIT_FOR_ME
        url = "https://ps-bap-client.becknprotocol.io/confirm"
        data = {
            "context": {
                "domain": "online-dispute-resolution:0.1.0",
                "location": {"country": {"code": "IND"}},
                "action": "confirm",
                "version": "1.1.0",
                "transaction_id": "",
                "message_id": "",
                "timestamp": "",
                "bap_uri": "https://ps-bap-network.becknprotocol.io",
                "bap_id": "ps-bap-network.becknprotocol.io",
                "bpp_id": self.variables["selected_provider"]["bpp_id"],
                "bpp_uri": self.variables["selected_provider"]["bpp_uri"],
                "ttl": "PT10M",
            },
            "message": {
                "order": {
                    "provider": {"id": self.variables["selected_provider"]["id"]},
                    "billing": {
                        "email": self.variables["c_email"],
                        "name": self.variables["c_name"],
                        "address": self.variables["c_address"],
                        "city": {"name": self.variables["c_city"]},
                    },
                    "fulfillments": [
                        {
                            "customer": {
                                "person": {"name": self.variables["c_name"]},
                                "contact": {
                                    "phone": self.variables["c_phone"],
                                    "email": self.variables["c_email"],
                                },
                            }
                        }
                    ],
                    "payments": [
                        {
                            "params": {
                                "amount": self.variables["selected_provider"]["quote"],
                                "currency": "INR",
                            },
                            "status": "PAID",
                        }
                    ],
                }
            },
        }
        response = requests.post(url, json=data)

        if response.status_code == 200:
            self.parse_confirm_response(response.json())
            logger.info(f"Request to cofirm: {response.status_code}")

        else:
            logger.error(
                f"Request to {url} failed. Status code: {response.status_code}\n Error msg: {response.text}"
            )
            self.cb(
                FSMOutput(
                    text="Sorry for the inconvinience, please try again after some time"
                )
            )

        self.status = Status.MOVE_FORWARD

    def parse_confirm_response(self, response_data):
        resp = response_data["responses"][0]
        self.variables["selected_provider"].update(
            {
                "agent_id": resp["message"]["order"]["fulfillments"][0]["agent"][
                    "person"
                ]["id"],
                "agent_name": resp["message"]["order"]["fulfillments"][0]["agent"][
                    "person"
                ]["name"],
                "payment_status": resp["message"]["order"]["payments"][0]["status"],
                "cancellation_fee": resp["message"]["order"]["cancellation_terms"][0][
                    "cancellation_fee"
                ]["percentage"],
                "docs_desc": resp["message"]["order"]["docs"][0]["descriptor"][
                    "short_desc"
                ],
                "docs_url": resp["message"]["order"]["docs"][0]["url"],
            }
        )
        info = self.variables["selected_provider"]
        message = f"Your dispute has been confirmed. You may contact your case manager, {info['agent_name']}.\n"

        if "contact" in resp["message"]["order"]["fulfillments"][0]:
            self.variables["selected_provider"].update(
                {
                    "agent_phone": resp["message"]["order"]["fulfillments"][0]["agent"][
                        "contact"
                    ]["phone"],
                    "agent_email": resp["message"]["order"]["fulfillments"][0]["agent"][
                        "contact"
                    ]["email"],
                }
            )
            message += f"Agent Email: {info['agent_email']}\n"
            message += f"Agent Phone: {info['agent_phone']}\n"
        message += f"Payment Status: {info['payment_status']}\n"
        message += f"Cancellation Fee: {info['cancellation_fee']}\n"
        message += f"{info['docs_desc']} {info['docs_url']}"
        self.cb(FSMOutput(text=message))

    def on_enter_ask_further_assistance(self):
        self.status = Status.WAIT_FOR_ME
        msg = "Do you want help with anything else? Type Yes or No."
        self.yes_or_no(msg)
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_end(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Thanks for giving us the opportunity to serve you!"))
        self.status = Status.MOVE_FORWARD


if __name__ == "__main__":

    def cb(x, **kwargs):
        if "file" in kwargs:
            print(f"File: {kwargs['file']}")
        return print(x)

    def generate_reference_id():
        return magic_string + str(uuid.uuid4())[:25] + magic_string

    fsm = FSM(cb, generate_reference_id)
    while True:
        i = input("Please provide input: ")
        fsm.process_input_or_callback(i)
