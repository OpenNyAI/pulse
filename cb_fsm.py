from datetime import datetime
import json
from dotenv import load_dotenv
import uuid
from enum import Enum
import requests

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
        "confirm_details",
        "fetch_lsp",
        "select_lsp",
        "confirm_lsp",
        "ask_for_question",
        "fetch_answer",
        "generate_response",
        "ask_for_another_question",
        "notice_draft",
        "drawer_name",
        "drawer_address",
        "payee_name",
        "payee_address",
        "cheque_info",
        "cheque_number",
        "cheque_date",
        "cheque_amount",
        "date_of_return_of_cheque",
        "reason",
        "generate_notice",
        "ask_for_lawyer",
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
        "send_link_odr",
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

        FSM.states.append("confirm_lsp")
        FSM.states.append("send_link")
        FSM.states.append("ask_further_assistance")

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
                "source": "ask_for_another_question",
                "dest": "ask_for_question",
                "conditions": "if_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_another_question",
                "dest": "ask_further_assistance",
                "conditions": "if_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_options_main",
                "dest": "confirm_details",
                "conditions": "is_consult_lawyer",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "confirm_details",
                "dest": "select_options_main",
                "conditions": "if_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "confirm_details",
                "dest": "fetch_lsp",
                "conditions": "if_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "select_lsp",
                "dest": "ask_to_select_lsp_again",
                "conditions": "is_not_valid_lsp",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_to_select_lsp_again",
                "dest": "select_lsp",
            }
        )

        transitions.append(
            {"trigger": "next", "source": "confirm_lsp", "dest": "send_link"}
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
                "dest": "drawer_name",
                "conditions": "is_notice_draft",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_lawyer",
                "dest": "confirm_details",
                "conditions": "if_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "ask_for_lawyer",
                "dest": "end",
                "conditions": "if_not_confirmed",
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
                "conditions": "if_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "odr_know_more",
                "dest": "explore_odr",
                "conditions": "if_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "explore_odr",
                "dest": "fetch_odr_providers",
                "conditions": "if_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "explore_odr",
                "dest": "ask_further_assistance",
                "conditions": "if_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "fix_provider",
                "dest": "collect_details",
                "conditions": "if_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "fix_provider",
                "dest": "fetch_odr_providers",
                "conditions": "if_not_confirmed",
            }
        )

        transitions.append(
            {
                "trigger": "next",
                "source": "confirm_odr_provider",
                "dest": "send_link_odr",
                "conditions": "if_confirmed",
            }
        )
        transitions.append(
            {
                "trigger": "next",
                "source": "confirm_odr_provider",
                "dest": "fetch_odr_providers",
                "conditions": "if_not_confirmed",
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
                "source": "confirm_odr_provider",
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

    # conditions
    def is_odr(self):
        return self.input == "4"

    def if_search_req_failed(self):
        return self.variables["search_req"]==False

    def if_select_req_failed(self):
        return self.variables["select_req"]==False

    def if_init_req_failed(self):
        return self.variables["init_req"]==False

    def on_enter_select_language(self):
        self.status = Status.WAIT_FOR_ME
        msg = self.input
        name = self.variables.get("name", "Mukul")
        self.cb(
            FSMOutput(
                text=f"Hey there! I'm the Cheque Bounce Bot. If your cheque bounces, I'm here to give you quick updates, answer your questions, and help you draft a demand notice. I can also connect you with experts who know how to handle cheque bounce issues. Let's make dealing with this situation a bit easier together!",
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

        services = [
            "Get more info",
            "Consult a lawyer",
            "Draft demand notice",
            "Online Dispute Resolution",
        ]
        text = "How can I help you today? Here are the four options for you:"
        self.create_options(text, services, "Menu Options")
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_select_options_main(self):
        self.variables["service_picked"] = self.input

    def is_know_more(self):
        return self.input == "1"

    def on_enter_ask_for_question(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(
            FSMOutput(
                text="Proceed to ask your question related to cheque bouncing below. Please ask only one question at a time and keep it brief."
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_ask_for_question(self):
        self.variables["query"] = self.input
        self.cb(
            FSMOutput(
                text="Thank you. I have received your question. I need a minute to prepare your answer."
            )
        )

    def on_enter_fetch_answer(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text=self.variables["query"], dest="rag"))
        self.cb(FSMOutput(text=f"*Your question*:\n{self.variables['query']}"))
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
   User: Is there any penalty for cheque bouncing?
   Bot: According to Negotiable Instruments Act, Banks in India may impose a penalty on the issuer for a bounced cheque, which can range from ₹200 to ₹600, depending on the bank's policy and the nature of the transaction.

   User: What's the legal precedent for cheque bouncing cases in Germany?
   Bot: Sorry, I don't know.

   User: What is the Capital of Vietnam?
   Bot: Sorry, this doesn't look like a legal question. I can only attempt to answer legal queries related to cheque bouncing, specific to India.


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
            OptionsListType(id="1", title="Yes"),
            OptionsListType(id="2", title="No"),
        ]

        self.cb(
            FSMOutput(
                text="Do you have any other question?",
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )

        self.status = Status.WAIT_FOR_USER_INPUT

    def is_consult_lawyer(self):
        return self.input == "2"

    def on_enter_fetch_lsp(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(
            FSMOutput(
                text="Thanks for your input. Here is a list of legal service providers who can help you with this process. You can click on each to see more information and a rough quote. Please select one."
            )
        )

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
            df = pd.read_excel("pulse/data/data.xlsx", usecols=columns.keys())
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
            print("Error: data.xlsx not found.")

        self.variables["providers"] = providers
        self.status = Status.MOVE_FORWARD

    def on_enter_select_lsp(self):
        self.status = Status.WAIT_FOR_ME
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_select_lsp(self):
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
        print(self.variables["selected_provider_name"])

    def is_not_valid_lsp(self):
        if self.input is None:
            return True
        try:
            self.input = int(self.input)
            if self.input < 1 or self.input > len(self.variables["providers"]):
                return True
        except Exception:
            return True
        return False

    def on_enter_ask_to_select_lsp_again(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(
            FSMOutput(
                text="Sorry, Your selected legal service provider is not valid.Please select a valid provider."
            )
        )
        self.status = Status.MOVE_FORWARD

    def on_enter_confirm_lsp(self):
        self.status = Status.WAIT_FOR_ME
        msg = self.input

        services = [
            OptionsListType(id="1", title="Yes"),
            OptionsListType(id="2", title="No"),
        ]

        self.cb(
            FSMOutput(
                text="Thanks. Are you sure you want to move forward with your selection? Please reply with 'Yes' or 'No'.",
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )

        self.status = Status.WAIT_FOR_USER_INPUT

    def if_confirmed(self):
        if self.input == "1":
            return True
        return False

    def if_not_confirmed(self):
        if self.input == "2":
            return True
        return False

    def on_enter_confirm_details(self):
        self.status = Status.WAIT_FOR_ME

        name = self.variables.get("name", "Mukul")
        cheque_bounce_number = self.variables.get("cheque_bounce_number", "XXXXX")
        bank_name = self.variables.get("bank_name", "ABI")
        bank_IFSC = self.variables.get("bank_IFSC", "ABI123456")
        bank_account_number = self.variables.get("bank_account_number", "1112223334")

        confirmation_message = (
            f"Please confirm the following details:\n"
            f"Name: {name}\n"
            f"Cheque Bounce Number: {cheque_bounce_number}\n"
            f"Bank Name: {bank_name}\n"
            f"Bank IFSC: {bank_IFSC}\n"
            f"Bank Account Number: {bank_account_number}"
        )
        services = [
            OptionsListType(id="1", title="Yes"),
            OptionsListType(id="2", title="No"),
        ]
        self.cb(
            FSMOutput(
                text=confirmation_message,
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_enter_send_link(self):
        self.status = Status.WAIT_FOR_ME
        link = "https://dummylinkforthecall/"
        message = f"Thanks for confirming. Here is the link for the call: {format(link)} \n Selected Provider: {self.variables['selected_provider_name']} \n Base Fee: {self.variables['selected_base_fee']}\n Available Slots: {self.variables['intent_fulfillment_time']}\n"
        output = FSMOutput(text=message)
        self.cb(output)
        self.status = Status.MOVE_FORWARD

    def on_enter_ask_further_assistance(self):
        self.status = Status.WAIT_FOR_ME

        services = [
            OptionsListType(id="1", title="Yes"),
            OptionsListType(id="2", title="No"),
        ]
        self.cb(
            FSMOutput(
                text="Do you want help with anything else? Type Yes or No.",
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

    def if_assistance_required(self):
        if self.input == "1":
            return True
        return False

    def if_assistance_not_required(self):
        if self.input == "2":
            return True
        return False

    def is_notice_draft(self):
        return self.input == "3"

    def on_enter_drawer_name(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter name of the drawer"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_drawer_name(self):
        self.variables["drawer_name"] = self.input

    def on_enter_drawer_address(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter address of the drawer"))

    def on_exit_drawer_address(self):
        self.variables["drawer_address"] = self.input

    def on_enter_payee_name(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter name of the payee"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_payee_name(self):
        self.variables["payee_name"] = self.input

    def on_enter_payee_address(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter address of payee"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_payee_address(self):
        self.variables["payee_address"] = self.input

    def on_enter_cheque_info(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter information of cheque bounced"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_cheque_info(self):
        self.variables["cheque_info"] = self.input

    def on_enter_cheque_number(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter number of cheque"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_cheque_number(self):
        self.variables["cheque_number"] = self.input

    def on_enter_cheque_date(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter cheque date"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_cheque_date(self):
        self.variables["cheque_date"] = self.input

    def on_enter_cheque_amount(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter amount of cheque"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_cheque_amount(self):
        self.variables["cheque_amount"] = self.input

    def on_enter_date_of_return_of_cheque(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter date of return of cheque"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_date_of_return_of_cheque(self):
        self.variables["date_of_return_of_cheque"] = self.input

    def on_enter_reason(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(FSMOutput(text="Please enter reason"))
        self.status = Status.WAIT_FOR_USER_INPUT

    def on_exit_reason(self):
        self.variables["reason"] = self.input

    def on_enter_generate_notice(self):
        self.status = Status.WAIT_FOR_ME
        file_path = os.path.join(
            os.getcwd(), "pulse", "data", "cheque_bouncing_notice_draft.pdf"
        )

        # Check if the file exists
        if os.path.exists(file_path):
            upload_file = UploadFile(
                filename="cheque_bouncing_notice_draft.pdf",
                path=file_path,
                mime_type="application/pdf",
            )
            self.cb(
                FSMOutput(
                    text="Downloaded",
                    file=upload_file,
                    dest="channel",
                    type=MessageType.DOCUMENT,
                )
            )
            self.status = Status.MOVE_FORWARD
        else:
            print("File not found:", file_path)
        self.status = Status.MOVE_FORWARD

    def on_enter_ask_for_lawyer(self):
        self.status = Status.WAIT_FOR_ME
        msg = self.input

        services = [
            OptionsListType(id="1", title="Yes"),
            OptionsListType(id="2", title="No"),
        ]

        self.cb(
            FSMOutput(
                text="Here is the first draft of your demand notice. Would you like to consult a lawyer on this?",
                type=MessageType.INTERACTIVE,
                options_list=services,
            )
        )
        self.status = Status.WAIT_FOR_USER_INPUT

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
            print("Error:", response.status_code, response.text)
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
            print("Error:", response.status_code, response.text)
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
        self.cb(
            FSMOutput(
                text="Please fill in the details below.",
                whatsapp_flow_id="276516008843199",
                whatsapp_screen_id="CB_DISPUTE_FORM",
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
        self.variables["r_name"] = form_data_dict["r_name"]
        self.variables["r_phone"] = form_data_dict["r_phone"]
        self.variables["r_email"] = form_data_dict["r_email"]
        self.variables["c_name"] = form_data_dict["c_name"]
        self.variables["c_phone"] = form_data_dict["c_phone"]
        self.variables["c_email"] = form_data_dict["c_email"]
        self.variables["c_address"] = form_data_dict["c_address"]
        self.variables["c_city"] = form_data_dict["c_city"]
        self.variables["dispute_details"] = form_data_dict["dispute_details"]
        if "claim_value" in form_data_dict: self.variables["claim_value"] = form_data_dict["claim_value"]
        self.status = Status.MOVE_FORWARD

    def on_enter_consent_form(self):
        self.status = Status.WAIT_FOR_ME
        self.cb(
            FSMOutput(
                text="Please fill in the ODR consent form below.",
                whatsapp_flow_id="1638693206954523",
                whatsapp_screen_id="CONSENT_FORM_FINAL",
                dest="channel",
                type=MessageType.FORM,
                form_token=str(uuid.uuid4()),
                menu_selector="Consent Form",
                menu_title="Consent Form",
                header="Consent Form",
            )
        )
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
            print("init respondent response:", response.json())
            self.variables["init_req"] = True

        else:
            print("Error:", response.status_code, response.text)
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
            print("init dispute details response:", response.json())
            self.variables["init_req"] = True

        else:
            print("Error:", response.status_code, response.text)
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
            print("init consent form response:", response.json())
            self.variables["init_req"] = True

        else:
            print("Error:", response.status_code, response.text)
            self.variables["init_req"] = False

        message = f"Rs. {self.variables['selected_provider']['quote']} is your fee, would you like to confirm your selection and initiate the ODR process?"
        self.yes_or_no(message)
        self.status = Status.WAIT_FOR_USER_INPUT

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

        else:
            print("Error:", response.status_code, response.text)
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
