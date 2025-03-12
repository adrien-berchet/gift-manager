(function($) {
    $.fn.initDataTableFilters = function (options) {
        // Default values with translations
        var defaults = {
            order: [[0, 'asc']],
            paging: true,
            searching: true,
            filterSelector: '.filter-icon',             // Filter icon to click on
            dropdownSelector: '.dropdown-filter',       // Dropdown to show/hide
            checkboxSelector: '.column-filter',         // Checkbox to filter on
            thFilterClass: '',                          // <th> class to filter on
        };

        var settings = $.extend(true, {}, defaults, options);

        var table = this.DataTable({
            "order": settings.order,
            "paging": settings.paging,
            "searching": settings.searching,
            "language": settings.language
        });

        function applyColumnFilter() {
            var selected = [];
            $(settings.checkboxSelector + ':checked').each(function(){
                selected.push($(this).val());
            });
            var regex = selected.length ? selected.join("|") : "";
            var colIndex = $('th.' + settings.thFilterClass).index();
            table.column(colIndex).search(regex, true, false).draw();
        }

        // Dropdown filter display
        $(settings.filterSelector).on('click', function(e) {
            e.stopPropagation();
            $(this).siblings(settings.dropdownSelector).toggle();
        });

        // Hide dropdown when clicking outside
        $(document).on('click', function() {
            $(settings.dropdownSelector).hide();
        });

        // When a checkbox changes, apply filter
        $(settings.checkboxSelector).on('change', function() {
            applyColumnFilter();
        });

        // At load time, apply the filter if some checkboxes are already checked
        applyColumnFilter();
    };
})(jQuery);
