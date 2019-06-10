/*
 * jquery document used to color the background of cells for the participant dashboard
 * identifies the max and min per ROW and highlights based on that gradient
 */

//main function that runs everything
(function(){
    angular
    .module("surveyBuilder")
    .controller('buttonController', ['$scope', '$window', function($scope, $window) {

        // change when they change the input
        $scope.calculateColor = calculateColor;
        $scope.setUp = setUp;
        $scope.createUrl = createUrl;
        $scope.maximum = $window.max;
        $scope.minimum = $window.min;
        setUp();

        ///////////////////////////////////////////////////////////////////////////////////////////////////////

        // function that originally sets up the colors before input
        function setUp() {
            if($window.max === 0 && $window.min === 0) {
                let max = null;
                let min = null;
                let table = $("#dashboard-datastream-table tbody");
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
                $scope.maximum = max;
                $scope.minimum = min;
            }
        }

        //update base url to include max and min endpoints
        function createUrl(base_url) {
            console.log("here");
            return (base_url + "&minimum=" + $scope.minimum + "&maximum=" + $scope.maximum)
        }

        // calculate new color scheme when user changes the values
        function calculateColor(value) {
            let max = $scope.maximum;
            let min = $scope.minimum;
            if(min < 0) {
                max -= min;
                value -= min;
                min = 0;
            }
            let adjusted_max = max - min;
            value -= min;
            let amount = value / adjusted_max;
            return {"background-color": `rgba(67, 165, 54, ${amount}`};
        }
    }]);
}());

        // $('#dashboard-datastream-table').DataTable();






