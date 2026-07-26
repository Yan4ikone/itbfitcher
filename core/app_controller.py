from excel.processor import (process_file_with_normalization, recalculate_codes)
from learning.importer import import_verified_file
from modules.ozon_auto_processor import OzonAutoProcessor


class AppController:

    def process(
        self,
        input_path,
        logger=None,
        progress_callback=None,
    ):
        return process_file_with_normalization(
            input_path=input_path,
            logger=logger,
            progress_callback=progress_callback,
        )

    def recalculate(
        self,
        input_path,
        logger=None,
        progress_callback=None,
    ):
        return recalculate_codes(
            input_path=input_path,
            logger=logger,
            progress_callback=progress_callback,
        )

    def learn_result(self, result_file,):
        return import_verified_file(result_file)

    def create_ozon_processor(
        self,
        input_path,
        logger=None,
        stats_callback=None,
        skip_filled=True,
    ):
        return OzonAutoProcessor(
            input_path,
            logger=logger,
            stats_callback=stats_callback,
            skip_filled=skip_filled,
        )