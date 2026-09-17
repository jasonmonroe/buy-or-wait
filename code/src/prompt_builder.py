# src/prompt_builder.py
# +---------------------------------------------------------------------------+
# |                            PROMPT BUILDER                                 |
# +---------------------------------------------------------------------------+


from code.src.constants import USER_PROMPT


class PromptBuilder:
    def __init__(self, dataset: dict):
        self.prompt = ""

        self._build(dataset)

    def _build(self, dataset: dict):

        data_dict = {}

        for key, value in dataset.items():
            pass

        return USER_PROMPT.format(request_xml=data_dict)

    def convert_to_xml(
        self,
        data_dict: dict,
    ):
        pass
