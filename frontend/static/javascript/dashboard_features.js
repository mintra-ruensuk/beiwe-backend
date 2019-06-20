/*
 * jquery document used to color the background of cells for the participant dashboard
 * identifies the max and min per ROW and highlights based on that gradient
 */

 // $('#dashboard-datastream-table').DataTable();

//main function that runs everything
(function(){
    angular
    .module("surveyBuilder")
    .controller('buttonController', ['$scope', '$window', function($scope, $window) {

        // change when they change the input
        $scope.calculateColor = calculateColor;
        $scope.setUp = setUp;
        $scope.createUrl = createUrl;
        $scope.createNewUrl = createNewUrl;
        $scope.evalColorRange = evalColorRange;
        $scope.removeColor = removeColor;
        $scope.addFlag = addFlag;
        $scope.removeFlag = removeFlag;
        $scope.checkFlag = checkFlag;
        $scope.flagExists = flagExists;
        $scope.createDateRangeUrl = createDateRangeUrl;
        $scope.addGradient = addGradient;
        $scope.flag_operator = null;
        $scope.flag_value = null;
        $scope.color_high_range = $window.color_high_range;
        $scope.color_low_range = $window.color_low_range;
        $scope.show_color = $window.show_color;
        $scope.all_flags_list = $window.all_flags_list;
        $scope.print_flags_dict = $window.print_flags_dict;
        $scope.base_past_url = $window.base_past_url;
        $scope.base_next_url = $window.base_next_url;
        $scope.start_date = $window.start_date;
        $scope.end_date = $window.end_date;
        setUp();

        // ------------------------ FUNCTIONS ----------------------- //

        function addGradient() {
            $scope.show_color = true;
        }

        function createDateRangeUrl(){
            const start_date = $scope.start_date.getFullYear() + "-" + ($scope.start_date.getMonth() + 1) + "-" + $scope.start_date.getDate();
            const end_date = $scope.end_date.getFullYear() + "-" + ($scope.end_date.getMonth() + 1) + "-" + $scope.end_date.getDate();
            const base_url = "?&start="+start_date+"&end="+end_date;
            let str = "";
            for(let flag_arr of $scope.all_flags_list){
                str += flag_arr[0]+","+flag_arr[1]+"*";
            }
            const flags = str.substr(0, str.length-1);
            $window.location = (base_url+"&color_low="+$scope.color_low_range+"&color_high="+$scope.color_high_range+"&show_color="+$scope.show_color+"&flags="+flags);
        }

        // check if flag is already present
        function flagExists(){
            let flag_exists = false;
            if ($scope.all_flags_list !== []) {
                for (let flag_arr of $scope.all_flags_list) {
                    if (flag_arr[0] === $scope.flag_operator && $scope.flag_value === flag_arr[1]) {
                        flag_exists = true;
                    }
                }
            }
            if($scope.flag_value === null || $scope.flag_operator === null){
                flag_exists = true;
            }
            return !flag_exists;
        }

        //remove flag that got clicked
        function removeFlag(flag){
            for(let i = 0; i < ($scope.all_flags_list).length; i++){
                if(($scope.all_flags_list[i][0]) === flag[0] && ($scope.all_flags_list[i][1]) === flag[1]){
                    $scope.all_flags_list.splice(i, 1);
                }
            }
        }

        //check if the flag is present
        function checkFlag(flag){
            return all_flags_list.includes([flag[0], flag[1]]);
        }

        //add flag
        function addFlag(){
            $scope.all_flags_list.push([$scope.flag_operator, $scope.flag_value]);
        }

        //create a new url for the next and past buttons
        function createNewUrl(base_url){
            let str = "";
            for(let flag_arr of $scope.all_flags_list){
                str += flag_arr[0]+","+flag_arr[1]+"*";
            }
            const flags = str.substr(0, str.length-1);
            $window.location = (base_url+"&color_low="+$scope.color_low_range+"&color_high="+$scope.color_high_range+"&show_color="+$scope.show_color+"&flags="+flags);
        }

        //remove color if widget is unclicked
        function removeColor(){
            $scope.show_color=false;
        }

        // evaluate color range to make sure min is smaller than max
        function evalColorRange(){
            return !($scope.color_high_range > $scope.color_low_range);
        }

        // function that originally sets up the colors before input
        function setUp() {
            if($window.color_high_range === 0 && $window.color_low_range === 0) {
                let max = null;
                let min = null;
                const table = $("#dashboard-datastream-table tbody");
                $("td", table).each(function(){
                    const num = Number($(this).attr("data-number"));
                    if (max === null) {
                        max = num;
                    }
                    if (min === null) {
                        min = num;
                    }
                    if (num > max){
                        max = num;
                    }
                    if (num < min){
                        min = num;
                    }
                });
                $scope.color_high_range = max;
                $scope.color_low_range = min;
            }
        }

        //update base url to include max and min endpoints
        function createUrl(base_url) {
            return (base_url + "&color_low=" + $scope.color_low_range + "&color_high=" + $scope.color_high_range)
        }

        // calculate new color scheme when user changes the values
        function calculateColor(value) {
            let amount_gradient = 0;
            let flag = false;
            if($scope.all_flags_list !== []){
                for(let flag_arr of $scope.all_flags_list){
                    if(flag_arr[0] === ">"){
                        if(flag_arr[1] < value){
                            flag = true;
                        }
                    }
                    else if(flag_arr[0] === "="){
                        if(flag_arr[1] === value){
                            flag = true;
                        }
                    }
                    else if(flag_arr[0] === "<"){
                        if(flag_arr[1] > value){
                            flag = true;
                        }
                    }
                }
            }

            if($scope.show_color && $scope.color_low_range < $scope.color_high_range) {
                const max = $scope.color_high_range;
                const min = $scope.color_low_range;
                const adjusted_max = max - min;
                value -= min;
                amount_gradient = value / adjusted_max;
            }

            if(flag === true){
                return{"border": "solid", "background-color": `rgba(67, 170, 54, ${amount_gradient}`};
            }
            else{
                return {"background-color": `rgba(67, 170, 54, ${amount_gradient}`};
            }
        }
    }]);
}());






